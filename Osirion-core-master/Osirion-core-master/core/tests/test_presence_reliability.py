import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.event_engine import EventEngine
from core.geometry import bbox_polygon_overlap_ratio
from core.tracking_processor import TrackingProcessor
from core.trackers.oc_sort import OCSortTrackerAdapter


TZ = ZoneInfo("Africa/Niamey")


def ts(hour, minute=0):
    return datetime(2026, 8, 24, hour, minute, tzinfo=TZ).timestamp()


def engine():
    return EventEngine(12, SimpleNamespace(
        ZONES_REFRESH_SECONDS=30,
        CROWD_MIN_SECONDS=3,
        OCCUPANCY_EMIT_INTERVAL=2,
        DWELL_MIN_SECONDS=1,
        OCCUPANCY_SMOOTH_SECONDS=0,
        DWELL_EXIT_GRACE_SECONDS=2,
        ZONE_MIN_PRESENCE_SECONDS=15,
        POST_ABSENCE_TOLERANCE_SECONDS=600,
        PRESENCE_BBOX_OVERLAP_MIN=0.50,
        PRESENCE_CANDIDATE_GRACE_SECONDS=5,
        TRACK_STATE_TTL_FRAMES=90,
        LINE_CROSS_MARGIN=0.02,
        LINE_CROSS_COOLDOWN_FRAMES=15,
        LINE_CROSS_MIN_AGE_FRAMES=3,
    ))


def schedule():
    return {
        "id": 2,
        "name": "UTC+1",
        "timezone": "Africa/Niamey",
        "segments": {"0": [["08:00", "17:00"]]},
        "absence_tolerance_s": 600,
    }


class PresenceReliabilityTests(unittest.TestCase):
    def test_quatre_captures_recouvrent_majoritairement_leurs_zones(self):
        # Boîtes rejouées avec yolo26s sur les quatre POST_VACANT du 26/08.
        cases = [
            (
                [[.696, .266], [.249, .346], [.284, .954], [.888, .761]],
                [557/1280, 439/720, 797/1280, 704/720],
            ),
            (
                [[.62, .478], [.301, .815], [.402, .988], [.985, .985], [.985, .79]],
                [746/1280, 424/720, 1017/1280, 699/720],
            ),
            (
                [[.131, .545], [.433, .34], [.637, .78], [.209, .993]],
                [302/1280, 343/720, 493/1280, 696/720],
            ),
            (
                [[.395, .973], [.369, .093], [.662, .051], [.93, .978]],
                [546/1280, 391/720, 837/1280, 719/720],
            ),
        ]
        ratios = [bbox_polygon_overlap_ratio(box, poly) for poly, box in cases]
        self.assertTrue(all(ratio >= 0.50 for ratio in ratios), ratios)

    def test_poste_accepte_corps_dans_zone_meme_si_pieds_dehors(self):
        eng = engine()
        poly = [[.395, .973], [.369, .093], [.662, .051], [.93, .978]]
        tracks = [{
            "track_id": 8,
            "x": .54,
            "y": .999,       # pied hors zone
            "bbox": [546/1280, 391/720, 837/1280, 719/720],
            "confidence": .73,
            "predicted": False,
        }]
        members, evidence = eng._presence_members(tracks, poly)
        self.assertEqual(members, {8})
        self.assertEqual(evidence[0]["membership"], "bbox_overlap")
        self.assertGreaterEqual(evidence[0]["overlap"], .50)

    def test_presence_provisoire_bloque_alerte_puis_confirmee(self):
        eng = engine()
        zone = {"name": "Guichet", "_sched": eng._prepare_schedule(schedule())}
        with patch("core.event_engine.event_dispatch.dispatch") as dispatch:
            eng._process_post(zone, 7, ts(8, 0), occupe=False)
            eng._process_post(
                zone, 7, ts(8, 10), occupe=False, provisional=True,
                evidence={"decision_state": "presence_pending"}, frame="visible",
            )
            eng._process_post(zone, 7, ts(8, 11), occupe=True, frame="visible")
        dispatch.assert_not_called()

    def test_candidat_live_ne_double_pas_tracker_et_detection_brute(self):
        eng = engine()
        all_day = schedule()
        all_day["segments"] = {str(day): [["00:00", "00:00"]] for day in range(7)}
        eng.zones = [{
            "id": 7,
            "name": "Guichet",
            "kind": "presence",
            "is_active": True,
            "polygon": [[.1, .1], [.9, .1], [.9, .95], [.1, .95]],
            "_sched": eng._prepare_schedule(all_day),
        }]
        eng.update_camera_health("online")
        track = {
            "track_id": 4, "x": .5, "y": .9,
            "bbox": [.4, .2, .6, .9], "confidence": .82, "predicted": False,
        }
        with patch("core.event_engine.event_dispatch.dispatch"):
            eng.process([track], detection_context={
                "inference_imgsz": 640,
                "person_detection_count": 1,
                "max_detection_confidence": .82,
                "person_detections": [{"bbox": track["bbox"], "confidence": .82}],
            })

        snapshot = eng.presence_snapshot()[0]
        self.assertEqual(snapshot["state"], "confirming")
        self.assertEqual(snapshot["candidate_count"], 1)
        self.assertEqual(snapshot["frame_person_detections"], 1)

    def test_candidat_repart_alerte_sur_frame_vide_sans_perdre_chrono(self):
        eng = engine()
        zone = {"name": "Guichet", "_sched": eng._prepare_schedule(schedule())}
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs))
            return True

        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, ts(8, 0), occupe=False)
            eng._process_post(
                zone, 7, ts(8, 10), occupe=False, provisional=True,
                evidence={"decision_state": "presence_pending"}, frame="visible",
            )
            eng._process_post(
                zone, 7, ts(8, 11), occupe=False, provisional=False,
                evidence={"decision_state": "vacant", "inference_imgsz": 640},
                frame="empty",
            )

        self.assertEqual([kind for kind, _ in emitted], ["POST_VACANT"])
        kwargs = emitted[0][1]
        self.assertEqual(kwargs["frame"], "empty")
        self.assertEqual(kwargs["meta"]["vacant_s"], 11 * 60)
        self.assertEqual(kwargs["meta"]["decision"]["decision_state"], "vacant")
        self.assertEqual(kwargs["meta"]["decision"]["last_candidate_age_s"], 60)

    def test_grace_candidat_couvre_un_rate_bref_entre_deux_echelles(self):
        eng = engine()
        zone = {"name": "Guichet", "_sched": eng._prepare_schedule(schedule())}
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs))
            return True

        start = ts(8, 0)
        candidate = ts(8, 10)
        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, start, occupe=False)
            eng._process_post(zone, 7, candidate, occupe=False, provisional=True)
            eng._process_post(zone, 7, candidate + 3, occupe=False)
            self.assertEqual(emitted, [])
            eng._process_post(zone, 7, candidate + 6, occupe=False)

        self.assertEqual([kind for kind, _ in emitted], ["POST_VACANT"])
        self.assertEqual(
            emitted[0][1]["meta"]["decision"]["candidate_grace_s"], 5
        )

    def test_multiscale_est_joue_par_blocs_de_quatre_frames(self):
        got = [
            TrackingProcessor._select_inference_imgsz(i, True, (640, 960), 960, 4)
            for i in range(1, 17)
        ]
        self.assertEqual(got, [640] * 4 + [960] * 4 + [640] * 4 + [960] * 4)
        self.assertEqual(
            TrackingProcessor._select_inference_imgsz(1, False, (640, 960), 960, 4),
            960,
        )

    def test_tracker_propage_la_confiance_yolo(self):
        tracker = OCSortTrackerAdapter(SimpleNamespace(
            det_thresh=.3, max_age=30, min_hits=3, iou_threshold=.3,
            delta_t=3, inertia=.2, use_byte=True, low_thresh=.1, max_coast=8,
        ))
        import numpy as np
        tracks = []
        for _ in range(4):
            tracks = tracker.update(
                np.asarray([[100, 100, 300, 500, .73]], dtype=float),
                [720, 1280], [720, 1280],
            )
        self.assertEqual(len(tracks), 1)
        self.assertAlmostEqual(tracks[0].score, .73, places=2)

    def test_presence_autorise_sursis_sur_bord_pendant_changement_echelle(self):
        import numpy as np

        tracker = OCSortTrackerAdapter(SimpleNamespace(
            det_thresh=.3, max_age=30, min_hits=3, iou_threshold=.3,
            delta_t=3, inertia=.2, use_byte=True, low_thresh=.1, max_coast=8,
        ))
        detection = np.asarray([[100, 100, 300, 720, .73]], dtype=float)
        for _ in range(4):
            tracks = tracker.update(detection, [720, 1280], [720, 1280])
        self.assertEqual(len(tracks), 1)

        tracks = tracker.update(
            np.empty((0, 5)), [720, 1280], [720, 1280],
            allow_border_coast=True,
        )
        self.assertEqual(len(tracks), 1)
        self.assertTrue(tracks[0].predicted)


if __name__ == "__main__":
    unittest.main()

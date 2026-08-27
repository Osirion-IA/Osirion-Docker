import unittest
import numpy as np
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.event_engine import EventEngine


TZ = ZoneInfo("Africa/Niamey")


def ts(day, hour, minute=0):
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ).timestamp()


def engine(staffing_policy=None):
    return EventEngine(12, SimpleNamespace(
        ZONES_REFRESH_SECONDS=30,
        CROWD_MIN_SECONDS=3,
        OCCUPANCY_EMIT_INTERVAL=2,
        DWELL_MIN_SECONDS=1,
        OCCUPANCY_SMOOTH_SECONDS=0,
        DWELL_EXIT_GRACE_SECONDS=2,
        ZONE_MIN_PRESENCE_SECONDS=0,
        POST_ABSENCE_TOLERANCE_SECONDS=600,
        PRESENCE_CANDIDATE_GRACE_SECONDS=5,
        TRACK_STATE_TTL_FRAMES=90,
        LINE_CROSS_MARGIN=0.02,
        LINE_CROSS_COOLDOWN_FRAMES=15,
        LINE_CROSS_MIN_AGE_FRAMES=3,
    ), staffing_policy=staffing_policy)


def schedule(segments=None):
    return {
        "id": 4,
        "name": "Agences Niger",
        "timezone": "Africa/Niamey",
        "segments": segments or {"0": [["08:00", "12:00"]]},
        "absence_tolerance_s": 600,
    }


def staffing_policy():
    return {
        "camera_name": "Guichets agence",
        "min_agents": 3,
        "max_agents": 5,
        "tolerance_s": 300,
        "schedule": schedule(),
    }


class PresenceScheduleTests(unittest.TestCase):
    def test_cloture_absence_transmet_image_fraiche(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        opening_frame = np.zeros((4, 4, 3), dtype=np.uint8)
        closing_frame = np.ones((4, 4, 3), dtype=np.uint8)
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs))
            return True

        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False, frame=opening_frame)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False, frame=opening_frame)
            eng._process_post(zone, 7, ts(24, 8, 17), occupe=True, frame=closing_frame)

        closure = next(kwargs for kind, kwargs in emitted if kind == "POST_ABSENCE")
        self.assertIs(closure["frame"], closing_frame)
        self.assertEqual(closure["meta"]["snapshot_origin"], "closure_frame")

    def test_cloture_technique_reutilise_image_ouverture(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        opening_frame = np.full((4, 4, 3), 7, dtype=np.uint8)
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs))
            return True

        eng.update_camera_health("online", now=ts(24, 8, 0))
        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False, frame=opening_frame)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False, frame=opening_frame)
            eng.update_camera_health("stalled", now=ts(24, 8, 12))

        closure = next(kwargs for kind, kwargs in emitted if kind == "POST_ABSENCE")
        self.assertIsNot(closure["frame"], opening_frame)
        np.testing.assert_array_equal(closure["frame"], opening_frame)
        self.assertEqual(
            closure["meta"]["snapshot_origin"], "vacancy_frame_fallback"
        )

    def test_signal_immediat_puis_episode_cloture(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs["meta"]))
            return True

        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False)
            eng._process_post(zone, 7, ts(24, 8, 17), occupe=True)

        self.assertEqual([kind for kind, _ in emitted], ["POST_VACANT", "POST_ABSENCE"])
        self.assertEqual(emitted[1][1]["absence_s"], 17 * 60)
        self.assertEqual(emitted[0][1]["episode_id"], emitted[1][1]["episode_id"])

    def test_file_pleine_ne_perd_pas_le_signal(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        eng._process_post(zone, 7, ts(24, 8, 0), occupe=False)

        with patch(
            "core.event_engine.event_dispatch.dispatch", side_effect=[False, True]
        ) as dispatch:
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False)
            self.assertFalse(eng._post_state[7]["reported"])
            eng._process_post(zone, 7, ts(24, 8, 11), occupe=False)

        self.assertTrue(eng._post_state[7]["reported"])
        self.assertEqual(dispatch.call_count, 2)

    def test_fin_de_creneau_clot_episode(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        emitted = []
        with patch(
            "core.event_engine.event_dispatch.dispatch",
            side_effect=lambda _cam, kind, **kwargs: emitted.append((kind, kwargs["meta"])) or True,
        ):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False)
            eng._process_post(zone, 7, ts(24, 12, 0), occupe=False)

        self.assertEqual(emitted[-1][0], "POST_ABSENCE")
        self.assertEqual(emitted[-1][1]["absence_s"], 4 * 3600)

    def test_creneau_de_nuit_est_continu(self):
        eng = engine()
        sched = eng._prepare_schedule(schedule({"0": [["22:00", "06:00"]]}))
        self.assertTrue(eng._in_work_segment(sched, ts(24, 23, 59)))
        self.assertTrue(eng._in_work_segment(sched, ts(25, 0, 0)))
        self.assertTrue(eng._in_work_segment(sched, ts(25, 5, 59)))
        self.assertFalse(eng._in_work_segment(sched, ts(25, 6, 0)))

    def test_journee_complete_minuit_a_minuit(self):
        eng = engine()
        sched = eng._prepare_schedule(schedule({"0": [["00:00", "00:00"]]}))
        self.assertTrue(eng._in_work_segment(sched, ts(24, 0, 0)))
        self.assertTrue(eng._in_work_segment(sched, ts(24, 23, 59)))
        self.assertFalse(eng._in_work_segment(sched, ts(25, 0, 0)))

    def test_zone_retiree_clot_episode_en_cours(self):
        eng = engine()
        zone = {"name": "Guichet 1", "_sched": eng._prepare_schedule(schedule())}
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs["meta"]))
            return True

        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False)
            eng._reconcile_post_states(set(), ts(24, 8, 30))

        self.assertNotIn(7, eng._post_state)
        self.assertEqual([kind for kind, _ in emitted], ["POST_VACANT", "POST_ABSENCE"])
        self.assertEqual(emitted[-1][1]["absence_s"], 30 * 60)

    def test_echec_api_conserve_configuration_chargee(self):
        eng = engine()
        eng.zones = [{"id": 3, "kind": "generic"}]
        eng.lines = [{"id": 8}]

        with patch("core.event_engine.fetch_zones", return_value=None), patch(
            "core.event_engine.fetch_lines", return_value=None
        ):
            eng._reload()

        self.assertEqual(eng.zones, [{"id": 3, "kind": "generic"}])
        self.assertEqual(eng.lines, [{"id": 8}])

    def test_sous_effectif_signale_puis_cloture(self):
        eng = engine(staffing_policy())
        emitted = []

        def dispatch(_cam, kind, **kwargs):
            emitted.append((kind, kwargs["meta"]))
            return True

        with patch("core.event_engine.event_dispatch.dispatch", side_effect=dispatch):
            eng._process_staffing(ts(24, 8, 0), count=2, has_presence_zones=True)
            eng._process_staffing(ts(24, 8, 5), count=2, has_presence_zones=True)
            eng._process_staffing(ts(24, 8, 12), count=3, has_presence_zones=True)

        self.assertEqual(
            [kind for kind, _ in emitted],
            ["STAFFING_LOW", "STAFFING_RECOVERED"],
        )
        self.assertEqual(emitted[0][1]["missing"], 1)
        self.assertEqual(emitted[1][1]["shortage_s"], 12 * 60)
        self.assertEqual(emitted[0][1]["episode_id"], emitted[1][1]["episode_id"])

    def test_effectif_ne_compte_pas_sans_zone_personnel(self):
        eng = engine(staffing_policy())
        with patch("core.event_engine.event_dispatch.dispatch") as dispatch:
            eng._process_staffing(ts(24, 8, 0), count=0, has_presence_zones=False)
            eng._process_staffing(ts(24, 8, 10), count=0, has_presence_zones=False)
        dispatch.assert_not_called()

    def test_comptage_reste_visible_sans_seuil_camera(self):
        eng = engine()
        eng.update_camera_health("online", now=ts(24, 9, 0))
        eng._process_staffing(ts(24, 9, 0), count=2, has_presence_zones=True)
        snapshot = eng.staffing_snapshot()
        self.assertFalse(snapshot["enabled"])
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["count"], 2)

    def test_etats_explicites_du_poste(self):
        eng = engine()
        zone = {
            "id": 7,
            "name": "Guichet 1",
            "kind": "presence",
            "is_active": True,
            "polygon": [[0.1, 0.2], [0.8, 0.2], [0.8, 0.9]],
            "min_presence_s": 5,
            "_sched": eng._prepare_schedule(schedule()),
        }
        eng.zones = [zone]
        eng.update_camera_health("online", now=ts(24, 8, 0))

        emitted = []
        with patch(
            "core.event_engine.event_dispatch.dispatch",
            side_effect=lambda _cam, kind, **kwargs: emitted.append(
                (kind, kwargs.get("meta") or {})
            ) or True,
        ):
            eng._process_post(
                zone, 7, ts(24, 8, 0), occupe=False,
                evidence={"decision_state": "vacant"},
            )
            self.assertEqual(
                eng.presence_snapshot(ts(24, 8, 0))[0]["state"],
                "vacancy_pending",
            )

            eng._process_post(
                zone, 7, ts(24, 8, 1), occupe=False, provisional=True,
                evidence={
                    "decision_state": "presence_pending",
                    "candidate_count": 1,
                },
            )
            self.assertEqual(
                eng.presence_snapshot(ts(24, 8, 1))[0]["state"],
                "confirming",
            )

            eng._process_post(
                zone, 7, ts(24, 8, 10), occupe=False,
                evidence={"decision_state": "vacant"},
            )
            self.assertEqual(
                eng.presence_snapshot(ts(24, 8, 10))[0]["state"],
                "vacant",
            )

            eng._process_post(
                zone, 7, ts(24, 8, 11), occupe=True,
                evidence={
                    "decision_state": "occupied",
                    "confirmed_count": 1,
                    "candidate_count": 2,
                    "membership_mode": "foot_or_bbox_overlap",
                    "bbox_overlap_threshold": 0.5,
                    "inference_imgsz": 960,
                    "frame_person_detections": 3,
                    "frame_max_confidence": 0.84,
                },
            )
            snapshot = eng.presence_snapshot(ts(24, 8, 11))[0]
            self.assertEqual(snapshot["state"], "occupied")
            self.assertEqual(snapshot["polygon"], zone["polygon"])
            self.assertEqual(snapshot["candidate_count"], 2)
            self.assertEqual(snapshot["bbox_overlap_threshold"], 0.5)
            self.assertEqual(snapshot["inference_imgsz"], 960)
            self.assertEqual(snapshot["frame_person_detections"], 3)
            self.assertEqual(snapshot["frame_max_confidence"], 0.84)

        self.assertEqual(
            [kind for kind, _ in emitted], ["POST_VACANT", "POST_ABSENCE"]
        )

    def test_coupure_camera_suspend_et_clot_les_chronos(self):
        eng = engine(staffing_policy())
        zone = {
            "id": 7,
            "name": "Guichet 1",
            "kind": "presence",
            "is_active": True,
            "_sched": eng._prepare_schedule(schedule()),
        }
        eng.zones = [zone]
        eng.update_camera_health("online", now=ts(24, 8, 0))
        emitted = []

        with patch(
            "core.event_engine.event_dispatch.dispatch",
            side_effect=lambda _cam, kind, **kwargs: emitted.append(
                (kind, kwargs.get("meta") or {})
            ) or True,
        ):
            eng._process_post(zone, 7, ts(24, 8, 0), occupe=False)
            eng._process_post(zone, 7, ts(24, 8, 10), occupe=False)
            eng._process_staffing(ts(24, 8, 0), count=1, has_presence_zones=True)
            eng._process_staffing(ts(24, 8, 5), count=1, has_presence_zones=True)

            eng.update_camera_health("stalled", now=ts(24, 8, 12))

        snapshot = eng.presence_snapshot(ts(24, 8, 12))[0]
        self.assertEqual(snapshot["state"], "unavailable")
        self.assertIsNone(snapshot["vacant_since"])
        self.assertEqual(eng.staffing_snapshot()["decision_state"], "unavailable")
        closures = [meta for kind, meta in emitted if kind == "POST_ABSENCE"]
        self.assertEqual(closures[-1]["resolution_reason"], "camera_unavailable")
        staffing_closures = [
            meta for kind, meta in emitted if kind == "STAFFING_RECOVERED"
        ]
        self.assertEqual(
            staffing_closures[-1]["resolution_reason"], "camera_unavailable"
        )

    def test_desactivation_politique_clot_sous_effectif(self):
        eng = engine(staffing_policy())
        emitted = []
        with patch(
            "core.event_engine.event_dispatch.dispatch",
            side_effect=lambda _cam, kind, **kwargs: emitted.append(kind) or True,
        ):
            eng._process_staffing(ts(24, 8, 0), count=1, has_presence_zones=True)
            eng._process_staffing(ts(24, 8, 5), count=1, has_presence_zones=True)
            self.assertTrue(eng.update_staffing_policy(None, now=ts(24, 8, 8)))

        self.assertEqual(emitted, ["STAFFING_LOW", "STAFFING_RECOVERED"])
        self.assertFalse(eng.staffing_snapshot()["enabled"])


if __name__ == "__main__":
    unittest.main()

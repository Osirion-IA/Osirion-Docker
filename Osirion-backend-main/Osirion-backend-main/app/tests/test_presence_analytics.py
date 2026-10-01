import unittest
from types import SimpleNamespace

from app.routes.analytics_routes import _filter_work_schedule, _presence_event_is_reliable
from app.models.events import EVENT_POST_ABSENCE, EVENT_POST_VACANT


class PresenceAnalyticsTests(unittest.TestCase):
    def test_filtre_sur_le_regime_historique_de_evenement(self):
        events = [
            SimpleNamespace(meta={"schedule_id": 2}),
            SimpleNamespace(meta={"schedule_id": 4}),
            SimpleNamespace(meta=None),
        ]
        self.assertEqual(_filter_work_schedule(events, 4), [events[1]])

    def test_absence_de_filtre_conserve_tout(self):
        events = [SimpleNamespace(meta={"schedule_id": 2}), SimpleNamespace(meta=None)]
        self.assertEqual(_filter_work_schedule(events, None), events)

    def test_qualite_presence_archivee_est_exclue(self):
        event = SimpleNamespace(
            event_type=EVENT_POST_ABSENCE,
            meta={"presence_data_quality": "archived", "resolution_reason": "presence_restored"},
        )
        self.assertFalse(_presence_event_is_reliable(event))

    def test_qualite_presence_tronquee_est_exclue_meme_en_schema_v2(self):
        event = SimpleNamespace(
            event_type=EVENT_POST_ABSENCE,
            meta={
                "presence_schema_version": 2,
                "presence_data_quality": "truncated",
                "resolution_reason": "camera_unavailable",
            },
        )
        self.assertFalse(_presence_event_is_reliable(event))

    def test_ancien_episode_camera_unavailable_marque_reliable_est_exclu(self):
        event = SimpleNamespace(
            event_type=EVENT_POST_ABSENCE,
            meta={
                "presence_schema_version": 2,
                "presence_data_quality": "reliable",
                "resolution_reason": "camera_unavailable",
            },
        )
        self.assertFalse(_presence_event_is_reliable(event))

    def test_qualite_presence_v2_est_fiable(self):
        event = SimpleNamespace(
            event_type=EVENT_POST_VACANT,
            meta={"presence_schema_version": 2, "presence_data_quality": "reliable"},
        )
        self.assertTrue(_presence_event_is_reliable(event))

    def test_premiers_evenements_corriges_restent_fiables(self):
        vacant = SimpleNamespace(event_type=EVENT_POST_VACANT, meta={"decision": {}})
        closed = SimpleNamespace(
            event_type=EVENT_POST_ABSENCE,
            meta={"resolution_reason": "presence_restored"},
        )
        self.assertTrue(_presence_event_is_reliable(vacant))
        self.assertTrue(_presence_event_is_reliable(closed))


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models.alerts import Alert
from app.models.events import Event
from app.services.retention_scheduler import purge_older_than


class RetentionTests(unittest.TestCase):
    def test_une_preuve_alerte_survit_a_la_purge_evenement(self):
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        old = datetime.utcnow() - timedelta(days=40)
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                Path("snapshots").mkdir()
                protected = Path("snapshots/protected.jpg")
                removable = Path("snapshots/removable.jpg")
                protected.write_bytes(b"proof")
                removable.write_bytes(b"ordinary")
                with Session(engine) as session:
                    ev_protected = Event(camera_id=1, event_type="POST_VACANT",
                                         snapshot_url=str(protected), timestamp=old)
                    ev_removable = Event(camera_id=1, event_type="DETECTION",
                                         snapshot_url=str(removable), timestamp=old)
                    session.add(ev_protected)
                    session.add(ev_removable)
                    session.commit()
                    session.refresh(ev_protected)
                    session.add(Alert(event_id=ev_protected.id, kind="absence",
                                      label="Poste vacant", snapshot_url=str(protected)))
                    session.commit()

                    stats = purge_older_than(session, 30)
                    self.assertEqual(len(session.exec(select(Event)).all()), 0)
                    self.assertEqual(len(session.exec(select(Alert)).all()), 1)
                self.assertTrue(protected.exists())
                self.assertFalse(removable.exists())
                self.assertEqual(stats["protected_snapshots"], 1)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()

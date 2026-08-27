import unittest

from pydantic import ValidationError

from app.schemas.camera_schema import CameraCreate


def payload(**overrides):
    data = {
        "cam_name": "Guichets agence",
        "rtsp_url": "rtsp://camera/stream",
    }
    data.update(overrides)
    return data


class CameraStaffingSchemaTests(unittest.TestCase):
    def test_configuration_complete_acceptee(self):
        camera = CameraCreate(**payload(
            staffing_max_agents=6,
            staffing_min_agents=4,
            staffing_tolerance_s=300,
            staffing_work_schedule_id=2,
        ))
        self.assertEqual(camera.staffing_min_agents, 4)
        self.assertEqual(camera.staffing_max_agents, 6)

    def test_configuration_desactivee_acceptee(self):
        camera = CameraCreate(**payload())
        self.assertIsNone(camera.staffing_min_agents)

    def test_edition_hikcentral_sans_url_acceptee_par_le_schema(self):
        camera = CameraCreate(cam_name="Entrée HikCentral")
        self.assertIsNone(camera.rtsp_url)

    def test_refuse_configuration_partielle(self):
        with self.assertRaises(ValidationError):
            CameraCreate(**payload(staffing_max_agents=6, staffing_min_agents=4))

    def test_refuse_minimum_superieur_au_maximum(self):
        with self.assertRaises(ValidationError):
            CameraCreate(**payload(
                staffing_max_agents=3,
                staffing_min_agents=4,
                staffing_work_schedule_id=2,
            ))

    def test_refuse_tolerance_trop_courte(self):
        with self.assertRaises(ValidationError):
            CameraCreate(**payload(staffing_tolerance_s=10))


if __name__ == "__main__":
    unittest.main()

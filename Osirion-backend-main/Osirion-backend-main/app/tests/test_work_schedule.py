import unittest

from pydantic import ValidationError

from app.schemas.work_schedule_schema import WorkScheduleCreate, WorkScheduleUpdate


class WorkScheduleSchemaTests(unittest.TestCase):
    def test_modele_par_defaut_h24_avec_pause_vendredi(self):
        schedule = WorkScheduleCreate(name="Agences H24")
        self.assertEqual(schedule.segments["0"], [["00:00", "00:00"]])
        self.assertEqual(
            schedule.segments["4"],
            [["00:00", "13:00"], ["14:00", "00:00"]],
        )

    def test_accepte_journee_complete_minuit_a_minuit(self):
        schedule = WorkScheduleCreate(
            name="Agence continue",
            segments={"0": [["00:00", "00:00"]]},
        )
        self.assertEqual(schedule.segments["0"], [["00:00", "00:00"]])

    def test_refuse_bornes_identiques_hors_minuit(self):
        with self.assertRaises(ValidationError):
            WorkScheduleCreate(
                name="Horaire ambigu",
                segments={"0": [["08:00", "08:00"]]},
            )

    def test_normalise_le_nom(self):
        schedule = WorkScheduleCreate(
            name="  Agences Niger  ",
            segments={"0": [["08:00", "12:00"]]},
        )
        self.assertEqual(schedule.name, "Agences Niger")

    def test_refuse_un_nom_vide(self):
        with self.assertRaises(ValidationError):
            WorkScheduleCreate(name="   ", segments={"0": [["08:00", "12:00"]]})

    def test_refuse_les_null_explicites_en_mise_a_jour(self):
        for field in ("name", "timezone", "segments", "absence_tolerance_s", "is_active"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                WorkScheduleUpdate(**{field: None})

    def test_accepte_un_creneau_de_nuit(self):
        schedule = WorkScheduleCreate(
            name="Équipe de nuit",
            segments={"0": [["22:00", "06:00"]]},
        )
        self.assertEqual(schedule.segments["0"], [["22:00", "06:00"]])

    def test_refuse_un_chevauchement_sur_le_jour_suivant(self):
        with self.assertRaises(ValidationError):
            WorkScheduleCreate(
                name="Nuit incohérente",
                segments={
                    "0": [["22:00", "06:00"]],
                    "1": [["05:00", "08:00"]],
                },
            )


if __name__ == "__main__":
    unittest.main()

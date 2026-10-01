import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.rules_schema import RuleCreate
from app.services.rule_engine import _scope_matches


class RuleGroupScopeSchemaTests(unittest.TestCase):
    def test_accepte_regle_poste_vacant_par_groupe(self):
        rule = RuleCreate(
            name="Absence Niger",
            trigger="POST_VACANT",
            work_schedule_id=4,
            kind="absence",
        )
        self.assertEqual(rule.work_schedule_id, 4)

    def test_refuse_severite_inconnue(self):
        with self.assertRaises(ValidationError):
            RuleCreate(
                name="Absence Niger",
                trigger="POST_VACANT",
                work_schedule_id=4,
                severity="urgent",
            )

    def test_refuse_identifiant_groupe_non_positif(self):
        with self.assertRaises(ValidationError):
            RuleCreate(
                name="Absence Niger",
                trigger="POST_VACANT",
                work_schedule_id=0,
            )

    def test_moteur_filtre_le_bon_groupe(self):
        rule = SimpleNamespace(zone_id=None, work_schedule_id=4)
        self.assertTrue(_scope_matches(rule, {"schedule_id": 4}))
        self.assertFalse(_scope_matches(rule, {"schedule_id": 5}))
        self.assertFalse(_scope_matches(rule, {}))

    def test_portees_zone_et_groupe_se_cumulent(self):
        rule = SimpleNamespace(zone_id=7, work_schedule_id=4)
        self.assertTrue(_scope_matches(rule, {"zone_id": 7, "schedule_id": 4}))
        self.assertFalse(_scope_matches(rule, {"zone_id": 8, "schedule_id": 4}))


if __name__ == "__main__":
    unittest.main()

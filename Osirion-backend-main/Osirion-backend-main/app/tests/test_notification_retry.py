"""Reprise des notifications d'alerte échouées (lot B du plan de corrections).

Campagne d'observation d'août 2026 : 55 alertes sur 574 jamais délivrées, toutes
sur des coupures DNS passagères du serveur de messagerie. L'envoi n'étant tenté
qu'une fois, un hoquet de quelques secondes perdait l'alerte définitivement.

Ces tests verrouillent le comportement attendu : on retente, on finit par
renoncer explicitement, et une alerte livrée n'est jamais renvoyée.
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models.alerts import Alert
# Instancier un Alert déclenche la configuration des mappers SQLAlchemy, qui exige
# que TOUS les modèles liés soient importés (Camera référence CameraGroup). Sans
# cet import, les tests passent isolément mais échouent en découverte, selon
# l'ordre de chargement.
from app.models import (  # noqa: F401 — résolution des relations ORM
    audit, camera_groups, camera_status_event, cameras, events,
    notification_config, rules, users, work_schedule, zones,
)
from app.services import notification_retry as nr
from app.services.rule_engine import NOTIFY_MAX_ATTEMPTS, _prochain_essai


def alerte(**overrides):
    base = dict(id=1, kind="queue", severity="warning", label="File saturée",
                reason="Saturation de file d'attente", camera_id=65,
                snapshot_url=None, created_at=datetime.utcnow(),
                notify_attempts=0, notified_at=None,
                notify_requested_channels="email")
    base.update(overrides)
    return Alert(**base)


class SessionFactice:
    """Session minimale : on ne teste pas l'ORM, seulement la logique de reprise."""

    def __init__(self):
        self.commits = 0

    def add(self, _obj):
        pass

    def commit(self):
        self.commits += 1


class BackoffTests(unittest.TestCase):
    def test_le_delai_croit_puis_on_renonce(self):
        """1, 5, 15, 30 min — puis abandon explicite plutôt qu'une livraison tardive."""
        avant = datetime.utcnow()
        delais = []
        for tentative in range(1, NOTIFY_MAX_ATTEMPTS):
            suivant = _prochain_essai(tentative)
            self.assertIsNotNone(suivant)
            delais.append(round((suivant - avant).total_seconds() / 60))
        self.assertEqual(delais, [1, 5, 15, 30])
        self.assertIsNone(
            _prochain_essai(NOTIFY_MAX_ATTEMPTS),
            "au-delà du plafond, aucune reprise ne doit être programmée",
        )


class RejouerTests(unittest.TestCase):
    def test_une_reprise_reussie_marque_l_alerte_livree(self):
        a = alerte(notify_attempts=2, notify_last_error="email: DNS timeout",
                   notify_next_retry_at=datetime.utcnow())
        with patch.object(nr, "send_email", return_value=(True, "ok")):
            livre = nr._rejouer(SessionFactice(), a, ["email"])
        self.assertTrue(livre)
        self.assertIsNotNone(a.notified_at)
        self.assertEqual(a.notified_channel, "email")
        self.assertIsNone(a.notify_next_retry_at, "plus rien à rejouer")
        self.assertIsNone(a.notify_last_error, "l'erreur passée doit être effacée")
        self.assertEqual(a.notify_attempts, 3)

    def test_un_echec_programme_une_nouvelle_tentative(self):
        a = alerte(notify_attempts=0)
        with patch.object(nr, "send_email", return_value=(False, "DNS timeout")):
            livre = nr._rejouer(SessionFactice(), a, ["email"])
        self.assertFalse(livre)
        self.assertIsNone(a.notified_at)
        self.assertEqual(a.notify_attempts, 1)
        self.assertIsNotNone(a.notify_next_retry_at, "l'alerte ne doit pas être perdue")
        self.assertIn("DNS timeout", a.notify_last_error)

    def test_le_canal_de_repli_sauve_l_alerte(self):
        """C'est tout l'intérêt d'un second canal : l'email tombe, le webhook passe."""
        a = alerte()
        with patch.object(nr, "send_email", return_value=(False, "DNS timeout")), \
             patch.object(nr, "send_webhook", return_value=(True, "202")):
            livre = nr._rejouer(SessionFactice(), a, ["email", "webhook"])
        self.assertTrue(livre)
        self.assertEqual(a.notified_channel, "webhook")

    def test_abandon_apres_le_plafond_de_tentatives(self):
        a = alerte(notify_attempts=NOTIFY_MAX_ATTEMPTS - 1)
        with patch.object(nr, "send_email", return_value=(False, "DNS timeout")):
            nr._rejouer(SessionFactice(), a, ["email"])
        self.assertEqual(a.notify_attempts, NOTIFY_MAX_ATTEMPTS)
        self.assertIsNone(a.notify_next_retry_at)
        self.assertIsNone(a.notified_at,
                          "l'alerte reste marquée non délivrée, jamais silencieusement close")

    def test_une_exception_d_envoi_ne_perd_pas_l_alerte(self):
        a = alerte()
        with patch.object(nr, "send_email", side_effect=OSError("socket fermée")):
            livre = nr._rejouer(SessionFactice(), a, ["email"])
        self.assertFalse(livre)
        self.assertIsNotNone(a.notify_next_retry_at)
        self.assertIn("OSError", a.notify_last_error)


class CanauxTests(unittest.TestCase):
    def test_la_reprise_respecte_les_canaux_de_la_regle(self):
        a = alerte(notify_requested_channels="email")
        self.assertEqual(nr._canaux_alert(a, ["email", "webhook"]), ["email"])

    def test_un_canal_ajoute_plus_tard_ne_recoit_pas_l_alerte(self):
        a = alerte(notify_requested_channels="webhook")
        self.assertEqual(nr._canaux_alert(a, ["email"]), [])

    def test_sans_canal_configure_aucun_envoi_n_est_tente(self):
        with patch.object(nr, "email_configured", return_value=False), \
             patch.object(nr, "webhook_configured", return_value=False):
            stats = nr.rejouer_les_echecs(SessionFactice())
        self.assertEqual(stats["reprises"], 0)
        self.assertIn("aucun canal", stats["motif"])


if __name__ == "__main__":
    unittest.main()

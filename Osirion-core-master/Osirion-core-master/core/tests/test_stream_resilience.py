"""Non-régression de la résilience d'ingestion vidéo (lot A du plan de corrections).

Contexte — campagne d'observation d'août 2026 : la passerelle HikCentral a renvoyé
44 902 fois HTTP 502 en sept jours. Deux défauts en ont découlé :

  A1. Un chemin MediaMTX dont l'URL ne se résolvait plus était IGNORÉ, donc laissé
      en place avec son jeton périmé. MediaMTX y relançait le relais ffmpeg toutes
      les ~6 s ; 78,8 % des relais mouraient en délai de démarrage et le parc était
      indisponible 34,3 % du temps.
  A2. Le Core, voyant ses caméras en difficulté, redemandait des URL avec
      refresh=True — contournant le cache backend et martelant une passerelle déjà
      en 502. Le mécanisme d'auto-guérison aggravait la panne.

Ces tests verrouillent les deux correctifs, ET la garde qui les rend sûrs : ne
jamais supprimer le chemin d'une caméra qui diffuse encore.
"""
import unittest
from unittest.mock import patch

from services import hik_stream_resolver as resolver
from services import mediamtx_path_service as mps


API = "http://mediamtx:9997"


def cam(cam_id, url=None):
    return {"id": cam_id, "cam_name": f"cam{cam_id}", "source_type": "hikcentral",
            "rtsp_url": url}


class PathReapingTests(unittest.TestCase):
    """A1 — un chemin dont l'URL ne se résout plus ne doit pas survivre… sauf s'il diffuse."""

    def _run(self, desired, existing, healthy=None):
        """Joue sync_paths et renvoie (chemins supprimés, chemins ajoutés, chemins patchés)."""
        with patch.object(mps, "_list_managed_paths", return_value=existing), \
             patch.object(mps, "_delete_path") as delete, \
             patch.object(mps, "_add_path") as add, \
             patch.object(mps, "_patch_path") as patch_:
            mps.sync_paths(API, desired, healthy=healthy)
        names = lambda m: [c.args[1] for c in m.call_args_list]
        return names(delete), names(add), names(patch_)

    def test_chemin_mort_supprime_quand_la_camera_ne_diffuse_plus(self):
        """URL non résolue + capture morte → le chemin est supprimé (fin de la boucle)."""
        deleted, added, patched = self._run(
            desired={9: cam(9, None)},
            existing={"cam9": "ffmpeg … -i rtsp://…/jeton_perime …"},
            healthy=set(),
        )
        self.assertEqual(deleted, ["cam9"])
        self.assertEqual(added, [])
        self.assertEqual(patched, [])

    def test_chemin_conserve_quand_la_camera_diffuse_encore(self):
        """URL non résolue MAIS capture vivante → on ne coupe pas un flux sain.

        Sans cette garde, une panne de passerelle couperait aussi toutes les caméras
        qui fonctionnaient — le correctif serait pire que le défaut.
        """
        deleted, added, patched = self._run(
            desired={9: cam(9, None)},
            existing={"cam9": "ffmpeg … -i rtsp://…/jeton_encore_valide …"},
            healthy={9},
        )
        self.assertEqual(deleted, [])
        self.assertEqual(added, [])
        self.assertEqual(patched, [])

    def test_aucun_chemin_a_supprimer_si_rien_nexiste(self):
        """URL non résolue et chemin jamais créé → aucune action, aucun bruit."""
        deleted, added, patched = self._run(
            desired={9: cam(9, None)}, existing={}, healthy=set(),
        )
        self.assertEqual((deleted, added, patched), ([], [], []))

    def test_url_resolue_recree_le_chemin(self):
        """Dès qu'une URL fraîche revient, le chemin est recréé normalement."""
        deleted, added, patched = self._run(
            desired={9: cam(9, "rtsp://passerelle/sms/HCPEurl/jeton_frais")},
            existing={}, healthy=set(),
        )
        self.assertEqual(added, ["cam9"])
        self.assertEqual(deleted, [])

    def test_un_reglage_modifie_est_propage_aux_chemins_existants(self):
        """Un changement de closeAfter/startTimeout doit déclencher un patch.

        La comparaison ne portait que sur la commande `runOnDemand` : tout réglage
        voisin modifié dans la config du Core restait silencieusement à son ancienne
        valeur sur les chemins déjà créés.
        """
        url = "rtsp://passerelle/sms/HCPEurl/jeton"
        conf_actuelle = mps._path_conf(url, "tcp", "30s", transcode=True,
                                       encoder="libx264", start_timeout="30s")
        with patch.object(mps, "_list_managed_paths",
                          return_value={"cam9": conf_actuelle}), \
             patch.object(mps, "_delete_path"), patch.object(mps, "_add_path"), \
             patch.object(mps, "_patch_path") as patch_:
            # Même URL, mais close_after passe de 30s à 180s.
            mps.sync_paths(API, {9: cam(9, url)}, close_after="180s",
                           transcode_encoder="libx264", healthy={9})
        self.assertEqual([c.args[1] for c in patch_.call_args_list], ["cam9"])
        self.assertEqual(patch_.call_args.args[2]["runOnDemandCloseAfter"], "180s")

    def test_configuration_identique_ne_declenche_aucun_appel(self):
        """Idempotence : rien ne bouge quand tout est déjà à jour (pas de bruit)."""
        url = "rtsp://passerelle/sms/HCPEurl/jeton"
        conf = mps._path_conf(url, "tcp", "180s", transcode=True,
                              encoder="libx264", start_timeout="30s")
        with patch.object(mps, "_list_managed_paths", return_value={"cam9": conf}), \
             patch.object(mps, "_delete_path") as d, patch.object(mps, "_add_path") as a, \
             patch.object(mps, "_patch_path") as p:
            mps.sync_paths(API, {9: cam(9, url)}, close_after="180s",
                           transcode_encoder="libx264", healthy={9})
        self.assertEqual((d.call_count, a.call_count, p.call_count), (0, 0, 0))

    def test_durees_equivalentes_ne_declenchent_pas_de_patch(self):
        """MediaMTX renvoie 3m0s après avoir reçu 180s : c'est la même durée."""
        url = "rtsp://passerelle/sms/HCPEurl/jeton"
        conf = mps._path_conf(url, "tcp", "180s", transcode=True,
                              encoder="libx264", start_timeout="30s")
        conf_api = {**conf, "runOnDemandCloseAfter": "3m0s"}
        with patch.object(mps, "_list_managed_paths", return_value={"cam9": conf_api}), \
             patch.object(mps, "_delete_path") as d, patch.object(mps, "_add_path") as a, \
             patch.object(mps, "_patch_path") as p:
            mps.sync_paths(API, {9: cam(9, url)}, close_after="180s",
                           transcode_encoder="libx264", healthy={9})
        self.assertEqual((d.call_count, a.call_count, p.call_count), (0, 0, 0))

    def test_panne_partielle_ne_touche_que_les_cameras_mortes(self):
        """Cas réel : la passerelle tombe, 2 caméras diffusent encore, 2 sont mortes."""
        deleted, _, _ = self._run(
            desired={9: cam(9, None), 10: cam(10, None),
                     24: cam(24, None), 62: cam(62, None)},
            existing={f"cam{i}": "ffmpeg …" for i in (9, 10, 24, 62)},
            healthy={9, 10},
        )
        self.assertEqual(sorted(deleted), ["cam24", "cam62"])

    def test_metrique_mediamtx_ne_retourne_jamais_les_urls(self):
        with patch.object(mps, "_list_managed_paths", return_value={
            "cam9": {"runOnDemand": "ffmpeg -i rtsp://secret"},
            "cam10": {"runOnDemand": "ffmpeg -i rtsp://secret2"},
        }):
            health = mps.managed_paths_health(API)
        self.assertEqual(health, {"managed_paths": 2, "api_reachable": True})


class ResolverBreakerTests(unittest.TestCase):
    """A2 — le résolveur doit cesser de solliciter une passerelle en panne."""

    def setUp(self):
        resolver._consecutive_failures = 0
        resolver._open_until = 0.0
        resolver._total_ok = resolver._total_fail = resolver._suppressed = 0

    @staticmethod
    def _reply(status=200, url="rtsp://passerelle/flux"):
        class R:
            status_code = status
            text = ""
            @staticmethod
            def json():
                return {"url": url}
        return R

    def test_le_disjoncteur_souvre_apres_le_seuil_dechecs(self):
        with patch.object(resolver, "request_with_auth", return_value=self._reply(502)) as call:
            for _ in range(resolver._FAIL_THRESHOLD):
                self.assertIsNone(resolver.resolve_stream_url(9))
            appels_avant = call.call_count
            # Au-delà du seuil, les appels suivants sont court-circuités.
            for _ in range(20):
                self.assertIsNone(resolver.resolve_stream_url(9))
            self.assertEqual(call.call_count, appels_avant,
                             "le disjoncteur ouvert doit empêcher tout appel réseau")
        sante = resolver.resolver_health()
        self.assertTrue(sante["hik_backoff_open"])
        self.assertEqual(sante["hik_resolve_suppressed"], 20)

    def test_le_rafraichissement_force_est_neutralise_des_le_premier_echec(self):
        """refresh=True contourne le cache backend : interdit dès que ça va mal."""
        with patch.object(resolver, "request_with_auth", return_value=self._reply(502)) as call:
            resolver.resolve_stream_url(9, refresh=True)          # 1er échec
            self.assertEqual(call.call_args.kwargs["params"]["refresh"], "true")
            resolver.resolve_stream_url(10, refresh=True)         # déjà dégradé
            self.assertEqual(call.call_args.kwargs["params"]["refresh"], "false")

    def test_une_seule_reussite_referme_le_disjoncteur(self):
        with patch.object(resolver, "request_with_auth", return_value=self._reply(502)):
            for _ in range(resolver._FAIL_THRESHOLD):
                resolver.resolve_stream_url(9)
        self.assertTrue(resolver.resolver_health()["hik_backoff_open"])

        resolver._open_until = 0.0          # le délai de backoff s'est écoulé
        with patch.object(resolver, "request_with_auth", return_value=self._reply(200)):
            self.assertEqual(resolver.resolve_stream_url(9), "rtsp://passerelle/flux")
        sante = resolver.resolver_health()
        self.assertFalse(sante["hik_backoff_open"])
        self.assertEqual(sante["hik_consecutive_failures"], 0)

    def test_une_reponse_200_sans_url_compte_comme_un_echec(self):
        with patch.object(resolver, "request_with_auth", return_value=self._reply(200, url=None)):
            self.assertIsNone(resolver.resolve_stream_url(9))
        self.assertEqual(resolver.resolver_health()["hik_resolve_fail"], 1)

    def test_les_compteurs_alimentent_les_metriques(self):
        """A4 : distinguer panne passerelle et panne caméra depuis metrics.jsonl seul."""
        for champ in ("hik_resolve_ok", "hik_resolve_fail", "hik_resolve_suppressed",
                      "hik_backoff_open", "hik_backoff_remaining_s",
                      "hik_consecutive_failures"):
            self.assertIn(champ, resolver.resolver_health())


if __name__ == "__main__":
    unittest.main()

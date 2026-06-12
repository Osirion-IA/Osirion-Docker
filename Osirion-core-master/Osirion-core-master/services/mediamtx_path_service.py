# services/mediamtx_path_service.py
"""
Gestion DYNAMIQUE des chemins MediaMTX (un par caméra) via son API HTTP (v3).

Au lieu de déclarer statiquement chaque caméra dans mediamtx.yml + .env
(MTX_PATHS_CAM<id>_SOURCE), le Core crée / met à jour / supprime à chaud le
chemin `cam<id>` à partir du rtsp_url renvoyé par le backend. Une caméra ajoutée
à chaud obtient ainsi automatiquement sa source MediaMTX, sans édition de fichier
ni redémarrage du conteneur.

L'API MediaMTX n'est PAS publiée vers l'hôte : seul le Core l'atteint, via le
réseau Docker interne (http://mediamtx:9997).
"""
import re
import requests
from typing import Dict, Any

from utils.logger import get_logger

logger = get_logger(__name__)

# Chemins GÉRÉS par le Core : "cam" + identifiant numérique. Le catch-all
# `all_others` et tout autre chemin (mire de test, push WHIP) sont IGNORÉS — on
# ne supprime jamais un chemin qu'on n'a pas créé.
_MANAGED_RE = re.compile(r'^cam\d+$')


def _mask(url: str) -> str:
    """Masque les credentials d'une URL RTSP pour les logs."""
    return re.sub(r'(rtsp://)([^@]+@)', r'\1***@', url or '')


def _ffmpeg_cmd(rtsp_url: str, transport: str) -> str:
    """Commande FFmpeg de RELAIS caméra → MediaMTX (sans ré-encodage).

    POURQUOI ce relais. Certaines caméras (typiquement Hikvision) émettent un
    flux H264 dont le SDP n'annonce pas `packetization-mode=1` (mode 0 /
    single-NAL, ou paramètre absent). gortsplib — le moteur RTSP de MediaMTX —
    REFUSE alors l'ingest direct ("unsupported packetization mode: 0" → 0 octet
    reçu), là où VLC/FFmpeg lisent le même flux sans broncher. On interpose donc
    FFmpeg : il pompe le flux caméra (tolérant) et le RE-PUBLIE dans MediaMTX en
    `-c:v copy` (AUCUN transcodage → coût CPU négligeable) avec une packetisation
    standard (mode 1) que MediaMTX accepte. L'audio est volontairement écarté
    (-an) : le pipeline est vidéo + métadonnées. `$MTX_PATH` et `$RTSP_PORT` sont
    injectés par MediaMTX à l'exécution → le flux est republié sur son propre
    chemin (cam<id>).

    NB : nécessite l'image `bluenviron/mediamtx:latest-ffmpeg` (ffmpeg embarqué).
    Les identifiants de l'URL doivent être URL-encodés (ex. '@' → '%40') : la
    commande est découpée sur les espaces, l'URL doit donc rester un seul token.
    """
    return (
        f"ffmpeg -nostdin -loglevel warning "
        f"-rtsp_transport {transport} -i {rtsp_url} "
        f"-an -c:v copy "
        f"-f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH"
    )


def _path_conf(rtsp_url: str, transport: str, close_after: str) -> Dict[str, Any]:
    """Configuration MediaMTX d'un chemin caméra : relais FFmpeg à la demande.

    Le relais n'est lancé QUE lorsqu'un lecteur demande le flux (runOnDemand),
    relancé automatiquement s'il s'arrête (coupure caméra) tant qu'un lecteur est
    présent (runOnDemandRestart), et fermé après `close_after` sans lecteur.
    """
    return {
        "runOnDemand": _ffmpeg_cmd(rtsp_url, transport),
        "runOnDemandRestart": True,
        "runOnDemandCloseAfter": close_after,
        "runOnDemandStartTimeout": "10s",
    }


def _list_managed_paths(api_base: str, timeout: float) -> Dict[str, str]:
    """Retourne {nom_chemin: commande_relais} des chemins gérés (cam<id>).

    La valeur est la commande `runOnDemand` (relais FFmpeg) qui embarque l'URL
    caméra — c'est elle qui sert de clé de comparaison pour décider d'un patch.
    Le repli sur `source` couvre d'anciens chemins créés avant le relais FFmpeg.
    """
    r = requests.get(
        f"{api_base}/v3/config/paths/list",
        params={"itemsPerPage": 1000},
        timeout=timeout,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    return {
        it["name"]: (it.get("runOnDemand") or it.get("source") or "")
        for it in items
        if _MANAGED_RE.match(it.get("name", ""))
    }


def sync_paths(api_base: str, desired: Dict[int, Dict[str, Any]],
               transport: str = "tcp", close_after: str = "30s",
               timeout: float = 5.0) -> None:
    """Réconcilie les chemins MediaMTX `cam<id>` avec l'ensemble de caméras voulu.

    `desired` : {cam_id: cam_dict}, où cam_dict["rtsp_url"] est l'URL RÉELLE de la
    caméra physique (celle du backend, avec credentials).

    Idempotent et best-effort : toute erreur réseau est logguée sans interrompre
    l'appelant — la caméra continue de tourner, et la prochaine réconciliation
    retentera. Robuste au redémarrage de MediaMTX : les chemins ajoutés via API ne
    sont pas persistés, ils sont donc recréés automatiquement au cycle suivant.
    """
    try:
        existing = _list_managed_paths(api_base, timeout)
    except Exception as e:
        logger.warning(
            f"Synchro MediaMTX : impossible de lister les chemins ({e}). "
            "Réessai au prochain cycle de supervision."
        )
        return

    desired_names = {f"cam{cid}": cam for cid, cam in desired.items()}

    # 1) Créations / mises à jour
    for name, cam in desired_names.items():
        rtsp_url = cam.get("rtsp_url")
        if not rtsp_url:
            logger.warning(
                f"Caméra {cam.get('id')} sans rtsp_url — chemin MediaMTX {name} ignoré."
            )
            continue
        conf = _path_conf(rtsp_url, transport, close_after)
        if name not in existing:
            _add_path(api_base, name, conf, timeout)
        elif existing[name] != conf["runOnDemand"]:
            _patch_path(api_base, name, conf, timeout)
        # sinon : déjà présent et à jour → rien à faire (pas de log = pas de bruit).

    # 2) Suppressions : chemins gérés qui ne correspondent plus à aucune caméra voulue
    #    (caméra désactivée / supprimée côté backend).
    for name in set(existing) - set(desired_names):
        _delete_path(api_base, name, timeout)


def _add_path(api_base: str, name: str, conf: Dict[str, Any], timeout: float) -> None:
    try:
        r = requests.post(f"{api_base}/v3/config/paths/add/{name}", json=conf, timeout=timeout)
        # 400 = le chemin existe déjà (course avec un autre ajout) → bascule en patch.
        if r.status_code == 400:
            _patch_path(api_base, name, conf, timeout)
            return
        r.raise_for_status()
        logger.info(f"Chemin MediaMTX {name} créé → {_mask(conf.get('runOnDemand', ''))}")
    except Exception as e:
        logger.error(f"Échec création chemin MediaMTX {name} : {e}")


def _patch_path(api_base: str, name: str, conf: Dict[str, Any], timeout: float) -> None:
    try:
        r = requests.patch(f"{api_base}/v3/config/paths/patch/{name}", json=conf, timeout=timeout)
        r.raise_for_status()
        logger.info(f"Chemin MediaMTX {name} mis à jour → {_mask(conf.get('runOnDemand', ''))}")
    except Exception as e:
        logger.error(f"Échec mise à jour chemin MediaMTX {name} : {e}")


def _delete_path(api_base: str, name: str, timeout: float) -> None:
    try:
        r = requests.delete(f"{api_base}/v3/config/paths/delete/{name}", timeout=timeout)
        if r.status_code not in (200, 404):  # 404 = déjà absent → OK
            r.raise_for_status()
        logger.info(f"Chemin MediaMTX {name} supprimé.")
    except Exception as e:
        logger.error(f"Échec suppression chemin MediaMTX {name} : {e}")

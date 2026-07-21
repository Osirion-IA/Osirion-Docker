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


def _ffmpeg_cmd(rtsp_url: str, transport: str, transcode: bool = False,
                encoder: str = "", encoder_flags: str = "") -> str:
    """Commande FFmpeg de RELAIS caméra → MediaMTX.

    POURQUOI ce relais. Certaines caméras (typiquement Hikvision) émettent un
    flux H264 dont le SDP n'annonce pas `packetization-mode=1` (mode 0 /
    single-NAL, ou paramètre absent). gortsplib — le moteur RTSP de MediaMTX —
    REFUSE alors l'ingest direct ("unsupported packetization mode: 0" → 0 octet
    reçu), là où VLC/FFmpeg lisent le même flux sans broncher. On interpose donc
    FFmpeg : il pompe le flux caméra (tolérant) et le RE-PUBLIE dans MediaMTX avec
    une packetisation standard (mode 1) que MediaMTX accepte. L'audio est
    volontairement écarté (-an) : le pipeline est vidéo + métadonnées. `$MTX_PATH`
    et `$RTSP_PORT` sont injectés par MediaMTX à l'exécution → le flux est republié
    sur son propre chemin (cam<id>).

    DEUX MODES DE COPIE VIDÉO :
      • transcode=False (défaut, caméras RTSP directes) → `-c:v copy` : AUCUN
        ré-encodage, coût CPU négligeable.
      • transcode=True (sources HikCentral) → ré-encodage vers `encoder` (ex.
        h264_nvenc en dev GPU, libx264 au déploiement). Les flux HikCentral sont
        en HEVC (H.265), que le WebRTC navigateur NE décode pas → on transcode en
        H.264. Le sous-flux ingéré (360p@10fps) rend ce transcodage très léger.

    NB : nécessite l'image `bluenviron/mediamtx:latest-ffmpeg` (ffmpeg embarqué).
    Les identifiants de l'URL doivent être URL-encodés (ex. '@' → '%40') : la
    commande est découpée sur les espaces, l'URL doit donc rester un seul token.
    """
    if transcode:
        flags = f" {encoder_flags}" if encoder_flags else ""
        video = f"-c:v {encoder}{flags}"
    else:
        video = "-c:v copy"
    return (
        f"ffmpeg -nostdin -loglevel warning "
        f"-rtsp_transport {transport} -i {rtsp_url} "
        f"-an {video} "
        f"-f rtsp -rtsp_transport tcp rtsp://localhost:$RTSP_PORT/$MTX_PATH"
    )


def _path_conf(rtsp_url: str, transport: str, close_after: str,
               transcode: bool = False, encoder: str = "", encoder_flags: str = "",
               start_timeout: str = "10s") -> Dict[str, Any]:
    """Configuration MediaMTX d'un chemin caméra : relais FFmpeg à la demande.

    Le relais n'est lancé QUE lorsqu'un lecteur demande le flux (runOnDemand),
    relancé automatiquement s'il s'arrête (coupure caméra) tant qu'un lecteur est
    présent (runOnDemandRestart), et fermé après `close_after` sans lecteur.
    `start_timeout` est allongé pour HikCentral (démarrage SMS lent à la 1re
    connexion).
    """
    return {
        "runOnDemand": _ffmpeg_cmd(rtsp_url, transport, transcode, encoder, encoder_flags),
        "runOnDemandRestart": True,
        "runOnDemandCloseAfter": close_after,
        "runOnDemandStartTimeout": start_timeout,
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
               timeout: float = 5.0, transcode_encoder: str = "h264_nvenc",
               transcode_flags: str = "", hik_start_timeout: str = "30s") -> None:
    """Réconcilie les chemins MediaMTX `cam<id>` avec l'ensemble de caméras voulu.

    `desired` : {cam_id: cam_dict}, où cam_dict["rtsp_url"] est l'URL RÉELLE de la
    caméra physique (pour les caméras HikCentral, elle a été résolue à la demande
    et injectée par la supervision avant l'appel). cam_dict["source_type"]
    ("rtsp"|"hikcentral") décide du transcodage HEVC→H.264 (sources HikCentral).

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
        # Les sources HikCentral émettent en HEVC (H.265) → transcodage H.264 requis
        # (WebRTC navigateur). Les caméras RTSP directes restent en copie (-c:v copy).
        is_hik = cam.get("source_type") == "hikcentral"
        conf = _path_conf(
            rtsp_url, transport, close_after,
            transcode=is_hik, encoder=transcode_encoder, encoder_flags=transcode_flags,
            start_timeout=(hik_start_timeout if is_hik else "10s"),
        )
        if name not in existing:
            _add_path(api_base, name, conf, timeout)
        elif existing[name] != conf["runOnDemand"]:
            _patch_path(api_base, name, conf, timeout)
        # sinon : déjà présent et à jour → rien à faire (pas de log = pas de bruit).

    # 2) Suppressions : chemins gérés qui ne correspondent plus à aucune caméra voulue
    #    (caméra désactivée / supprimée côté backend).
    for name in set(existing) - set(desired_names):
        _delete_path(api_base, name, timeout)


def ensure_preview_path(api_base: str, cam_id: int, rtsp_url: str,
                        transport: str = "tcp", encoder: str = "libx264",
                        encoder_flags: str = "", start_timeout: str = "30s",
                        close_after: str = "15s", timeout: float = 5.0) -> str:
    """Crée/MAJ un chemin MediaMTX `preview<id>` pour PRÉVISUALISER une caméra du
    catalogue SANS la traiter (pas d'IA, is_active reste False).

    Le nom `preview<id>` est HORS du regex géré (`^cam\\d+$`) → la réconciliation du
    Core ne le liste ni ne le supprime jamais (pas de conflit avec `cam<id>`).
    `runOnDemand` + `close_after` court : le relais transcodé ne tourne QUE pendant
    la prévisualisation (tant qu'un lecteur WHEP est là), puis s'arrête. Renvoie le
    nom du chemin (à passer au lecteur WHEP)."""
    name = f"preview{cam_id}"
    conf = _path_conf(rtsp_url, transport, close_after, transcode=True,
                      encoder=encoder, encoder_flags=encoder_flags,
                      start_timeout=start_timeout)
    _add_path(api_base, name, conf, timeout)  # bascule en patch si déjà présent (400)
    return name


def delete_preview_path(api_base: str, cam_id: int, timeout: float = 5.0) -> None:
    """Supprime le chemin de prévisualisation `preview<id>` (nettoyage best-effort)."""
    _delete_path(api_base, f"preview{cam_id}", timeout)


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

# app/services/hikcentral_connector.py
"""
Connecteur HikCentral Professional OpenAPI (gateway « Artemis », auth AK/SK).

Validé en étape 1 (script de diagnostic) :
- Auth = signature HMAC-SHA256 (AppKey/AppSecret) + en-tête userId (Linked User).
- Catalogue : /resource/v1/regions (areas = groupes) + /resource/v1/cameras.
- Flux live : /video/v1/cameras/previewURLs avec protocol="rtsp_s" → URL RTSP
  STANDARD, auto-suffisante (auth embarquée), lisible par ffmpeg/MediaMTX.

Config via settings.HIK_* (config.py). Vide = connecteur désactivé.
Best-effort : lève HikCentralError avec un message clair, jamais un traceback brut.
"""
import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import uuid

import requests
from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.utils.security_utils import decrypter

logger = logging.getLogger(__name__)

# Cache mémoire des URLs de flux résolues. L'URL rtsp_s est STABLE et de longue
# durée (>5 min validé) → inutile d'appeler HikCentral à chaque cycle de
# supervision du Core. TTL généreux mais < durée de vie de l'URL. Clé =
# (cameraIndexCode, streamType). `resolve_stream_url(force=True)` (retry) et
# `invalidate_stream_url` contournent/vident le cache.
STREAM_URL_TTL_SECONDS = 240
_url_cache: dict = {}
_url_cache_lock = threading.Lock()

if not settings.HIK_VERIFY_SSL:
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass


class HikCentralError(RuntimeError):
    """Erreur applicative HikCentral (config manquante, code != 0, réseau)."""


# Config de CONNEXION effective (base HikCentralConfig si renseignée, sinon .env).
# En cache mémoire (évite un hit DB par appel), invalidée à chaque enregistrement
# via invalidate_config(). Les champs TECHNIQUES (verify_ssl, stream_type) viennent
# TOUJOURS de settings/.env.
_cfg_cache: "dict | None" = None
_cfg_lock = threading.Lock()


def _load_effective_config() -> dict:
    """Fusionne la config de connexion base (prioritaire) et .env (repli)."""
    host = app_key = app_secret = user_id = None
    source = "env"
    try:
        from app.models.hikcentral_config import HikCentralConfig  # import tardif (évite cycles)
        with Session(engine) as s:
            row = s.get(HikCentralConfig, 1)
        if row and (row.host or row.app_key or row.app_secret_enc or row.user_id):
            host = row.host or None
            app_key = row.app_key or None
            app_secret = decrypter(row.app_secret_enc) if row.app_secret_enc else None
            user_id = row.user_id or None
            source = "db"
    except Exception:
        # Table absente (avant migration) ou DB indispo → repli .env, jamais bloquant.
        logger.debug("[hik] lecture config base impossible → repli .env", exc_info=True)
    return {
        "host": host or settings.HIK_HOST,
        "app_key": app_key or settings.HIK_APP_KEY,
        "app_secret": app_secret or settings.HIK_APP_SECRET,
        "user_id": user_id or settings.HIK_USER_ID,
        "verify_ssl": settings.HIK_VERIFY_SSL,     # technique → toujours .env
        "stream_type": settings.HIK_STREAM_TYPE,   # technique → toujours .env
        "source": source,
    }


def get_config() -> dict:
    global _cfg_cache
    with _cfg_lock:
        if _cfg_cache is None:
            _cfg_cache = _load_effective_config()
        return _cfg_cache


def invalidate_config() -> None:
    """À appeler après tout enregistrement de la config de connexion (UI)."""
    global _cfg_cache
    with _cfg_lock:
        _cfg_cache = None
    with _url_cache_lock:
        _url_cache.clear()   # les URLs en cache dépendent des credentials


def is_configured() -> bool:
    c = get_config()
    return bool(c["host"] and c["app_key"] and c["app_secret"] and c["user_id"])


def _signed_request(cfg: dict, path: str, body: dict) -> dict:
    """POST signé (AK/SK) avec des credentials EXPLICITES → data.data (code==0 exigé).
    Partagé par _post (config effective) et test_connection (creds à valider)."""
    if not (cfg.get("host") and cfg.get("app_key") and cfg.get("app_secret") and cfg.get("user_id")):
        raise HikCentralError("HikCentral non configuré (hôte / App Key / App Secret / Linked User).")

    method, accept = "POST", "application/json"
    ctype = "application/json;charset=UTF-8"
    body_str = json.dumps(body, ensure_ascii=False)
    content_md5 = base64.b64encode(hashlib.md5(body_str.encode("utf-8")).digest()).decode("utf-8")
    ts, nonce = str(int(time.time() * 1000)), str(uuid.uuid4())
    signed = {"x-ca-key": cfg["app_key"], "x-ca-timestamp": ts, "x-ca-nonce": nonce}

    sign_str = f"{method}\n{accept}\n{content_md5}\n{ctype}\n"
    for k in sorted(signed):
        sign_str += f"{k}:{signed[k]}\n"
    sign_str += path
    signature = base64.b64encode(
        hmac.new(cfg["app_secret"].encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {
        "Accept": accept, "Content-Type": ctype, "Content-MD5": content_md5,
        "userId": cfg["user_id"], "X-Ca-Key": cfg["app_key"],
        "X-Ca-Signature": signature, "X-Ca-Signature-Headers": ",".join(sorted(signed)),
        "X-Ca-Timestamp": ts, "X-Ca-Nonce": nonce,
    }
    host = cfg["host"].rstrip("/")
    try:
        r = requests.post(host + path, headers=headers, data=body_str.encode("utf-8"),
                          verify=cfg.get("verify_ssl", False), timeout=25)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as exc:
        raise HikCentralError(f"réseau/HTTP sur {path} : {exc}") from exc
    if str(data.get("code")) != "0":
        raise HikCentralError(f"{path} → code {data.get('code')} : {data.get('msg')}")
    return data.get("data") or {}


def _post(path: str, body: dict) -> dict:
    """POST signé avec la config de connexion EFFECTIVE (base > .env)."""
    return _signed_request(get_config(), path, body)


def test_connection(cfg: dict) -> None:
    """Valide des credentials par un appel LÉGER (regions, 1 élément). Lève
    HikCentralError si la connexion / l'authentification échoue."""
    _signed_request(cfg, "/artemis/api/resource/v1/regions", {"pageNo": 1, "pageSize": 1})


def get_regions() -> dict:
    """Toutes les Areas (groupes, ex. « Agence Niamey »). indexCode -> {name, parent}."""
    out, page = {}, 1
    while True:
        d = _post("/artemis/api/resource/v1/regions", {"pageNo": page, "pageSize": 500})
        lst = d.get("list") or []
        for a in lst:
            out[str(a.get("indexCode"))] = {"name": a.get("name"), "parent": a.get("parentIndexCode")}
        if len(lst) < 500:
            break
        page += 1
    return out


def get_all_cameras() -> list:
    """Toutes les caméras (toutes les pages). Chacune porte cameraIndexCode,
    cameraName, regionIndexCode (son groupe) et status (1=en ligne, 2=hors-ligne)."""
    out, page = [], 1
    while True:
        d = _post("/artemis/api/resource/v1/cameras", {"pageNo": page, "pageSize": 500})
        lst = d.get("list") or []
        out.extend(lst)
        if len(lst) < 500:
            break
        page += 1
    return out


def get_preview_url(camera_index_code: str, stream_type: int = None,
                    protocol: str = "rtsp_s", transmode: int = 1) -> str:
    """URL de flux LIVE (RTSP standard via rtsp_s). transmode 1=TCP. Résolue à la demande."""
    if stream_type is None:
        stream_type = get_config()["stream_type"]
    d = _post("/artemis/api/video/v1/cameras/previewURLs", {
        "cameraIndexCode": str(camera_index_code), "streamType": int(stream_type),
        "protocol": protocol, "transmode": int(transmode),
    })
    url = d.get("url")
    if not url:
        raise HikCentralError(f"previewURLs sans url pour la caméra {camera_index_code}")
    return url


def resolve_stream_url(camera_index_code: str, stream_type: int = None,
                       ttl: int = STREAM_URL_TTL_SECONDS, force: bool = False) -> str:
    """URL de flux résolue AVEC cache (voir _url_cache).

    force=True (retry) : ignore le cache et ré-interroge HikCentral — sert à vérifier
    que la liaison agence répond ET à récupérer une éventuelle nouvelle URL après une
    coupure. La valeur fraîche remplace l'entrée en cache.
    """
    if stream_type is None:
        stream_type = get_config()["stream_type"]
    key = (str(camera_index_code), int(stream_type))
    now = time.monotonic()
    if not force:
        with _url_cache_lock:
            hit = _url_cache.get(key)
            if hit and hit[1] > now:
                return hit[0]
    url = get_preview_url(camera_index_code, stream_type=stream_type)
    with _url_cache_lock:
        _url_cache[key] = (url, now + ttl)
    return url


def invalidate_stream_url(camera_index_code: str, stream_type: int = None) -> None:
    """Purge l'URL en cache d'une caméra (prochaine résolution = appel frais)."""
    if stream_type is None:
        stream_type = get_config()["stream_type"]
    with _url_cache_lock:
        _url_cache.pop((str(camera_index_code), int(stream_type)), None)

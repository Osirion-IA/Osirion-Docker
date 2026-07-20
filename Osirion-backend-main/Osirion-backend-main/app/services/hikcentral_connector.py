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

from app.config import settings

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


def is_configured() -> bool:
    return bool(settings.HIK_HOST and settings.HIK_APP_KEY and settings.HIK_APP_SECRET and settings.HIK_USER_ID)


def _post(path: str, body: dict) -> dict:
    """POST signé (AK/SK) vers l'OpenAPI Gateway. Retourne data.data (code==0 exigé)."""
    if not is_configured():
        raise HikCentralError("HikCentral non configuré (HIK_HOST / HIK_APP_KEY / HIK_APP_SECRET / HIK_USER_ID).")

    method, accept = "POST", "application/json"
    ctype = "application/json;charset=UTF-8"
    body_str = json.dumps(body, ensure_ascii=False)
    content_md5 = base64.b64encode(hashlib.md5(body_str.encode("utf-8")).digest()).decode("utf-8")
    ts, nonce = str(int(time.time() * 1000)), str(uuid.uuid4())
    signed = {"x-ca-key": settings.HIK_APP_KEY, "x-ca-timestamp": ts, "x-ca-nonce": nonce}

    sign_str = f"{method}\n{accept}\n{content_md5}\n{ctype}\n"
    for k in sorted(signed):
        sign_str += f"{k}:{signed[k]}\n"
    sign_str += path
    signature = base64.b64encode(
        hmac.new(settings.HIK_APP_SECRET.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    headers = {
        "Accept": accept, "Content-Type": ctype, "Content-MD5": content_md5,
        "userId": settings.HIK_USER_ID, "X-Ca-Key": settings.HIK_APP_KEY,
        "X-Ca-Signature": signature, "X-Ca-Signature-Headers": ",".join(sorted(signed)),
        "X-Ca-Timestamp": ts, "X-Ca-Nonce": nonce,
    }
    host = settings.HIK_HOST.rstrip("/")
    try:
        r = requests.post(host + path, headers=headers, data=body_str.encode("utf-8"),
                          verify=settings.HIK_VERIFY_SSL, timeout=25)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as exc:
        raise HikCentralError(f"réseau/HTTP sur {path} : {exc}") from exc
    if str(data.get("code")) != "0":
        raise HikCentralError(f"{path} → code {data.get('code')} : {data.get('msg')}")
    return data.get("data") or {}


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
        stream_type = settings.HIK_STREAM_TYPE
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
        stream_type = settings.HIK_STREAM_TYPE
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
        stream_type = settings.HIK_STREAM_TYPE
    with _url_cache_lock:
        _url_cache.pop((str(camera_index_code), int(stream_type)), None)

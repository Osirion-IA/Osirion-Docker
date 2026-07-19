# core/event_dispatch.py
"""
Dispatcher d'événements DÉCOUPLÉ.

L'Event Engine (thread caméra) pousse des événements dans une file via dispatch()
— NON bloquant. Un thread dédié unique consomme la file et fait le POST HTTP
(/events/add) en fire-and-forget. Le thread caméra n'est JAMAIS bloqué par le
réseau. Événements discrets (occupation throttlée, attroupement rare, comptages)
→ volume faible.
"""
import json
import queue as _queue
import threading
from typing import Optional, Dict, Any

import cv2

from utils.api_client import request_with_auth
from utils.logger import get_logger

logger = get_logger(__name__)

_MAXSIZE = 256
_queue_obj: "Optional[_queue.Queue]" = None
_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def start() -> None:
    """Démarre le thread dispatcher (idempotent)."""
    global _queue_obj, _thread, _stop
    if _thread is not None and _thread.is_alive():
        return
    _stop = threading.Event()
    _queue_obj = _queue.Queue(maxsize=_MAXSIZE)
    _thread = threading.Thread(target=_run, name="event-dispatch", daemon=True)
    _thread.start()
    logger.info("[event-dispatch] démarré.")


def stop() -> None:
    """Arrête proprement le thread dispatcher."""
    global _thread
    _stop.set()
    if _queue_obj is not None:
        try:
            _queue_obj.put_nowait(None)
        except Exception:
            pass
    if _thread is not None:
        _thread.join(timeout=3)
        _thread = None


def dispatch(camera_id: int, event_type: str,
             meta: Optional[Dict[str, Any]] = None,
             frame=None, confidence: float = 0.0) -> None:
    """Enfile un événement (non bloquant). Abandonné silencieusement si file pleine."""
    if _queue_obj is None:
        return
    try:
        _queue_obj.put_nowait({
            "camera_id": camera_id, "event_type": event_type,
            "meta": meta, "frame": frame, "confidence": confidence,
        })
    except _queue.Full:
        logger.warning("[event-dispatch] file pleine — événement abandonné.")


def _run() -> None:
    while not _stop.is_set():
        try:
            item = _queue_obj.get(timeout=0.5)
        except _queue.Empty:
            continue
        if item is None:
            continue
        try:
            _send(item)
        except Exception as e:
            logger.debug(f"[event-dispatch] envoi échoué : {e}")


def _send(item: Dict[str, Any]) -> None:
    data = {
        "camera_id": str(item["camera_id"]),
        "event_type": item["event_type"],
        "confidence": str(item.get("confidence", 0.0)),
    }
    if item.get("meta") is not None:
        data["meta"] = json.dumps(item["meta"], ensure_ascii=False)

    files = None
    frame = item.get("frame")
    if frame is not None:
        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            files = {"image": ("event.jpg", buf.tobytes(), "image/jpeg")}

    # request_with_auth ne pose QUE l'en-tête d'auth → requests ajoute lui-même le
    # Content-Type multipart (avec boundary) quand files est fourni. Ré-auth + retry
    # automatiques sur 401/coupure réseau.
    request_with_auth("POST", "/events/add", data=data, files=files, timeout=5)

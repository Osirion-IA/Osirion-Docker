import asyncio
import aiohttp
import cv2
import numpy as np
from utils.auth_utils import get_auth_headers, API_URL
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # secondes


async def send_event_async(
    session: aiohttp.ClientSession,
    frame: np.ndarray,
    camera_id: int,
    person_id: int,
    event_type: str,
    confidence: float
):
    URL = f"{API_URL}/events/add"

    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        logger.error("Erreur lors de l'encodage de l'image")
        return False

    image_bytes = buffer.tobytes()

    for attempt in range(1, MAX_RETRIES + 1):
        headers = get_auth_headers()

        form = aiohttp.FormData()
        form.add_field(
            "image",
            image_bytes,
            filename="event.jpg",
            content_type="image/jpeg"
        )
        form.add_field("camera_id", str(camera_id))
        form.add_field("person_id", str(person_id))
        form.add_field("event_type", event_type)
        form.add_field("confidence", str(confidence))

        try:
            async with session.post(
                URL,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:

                if response.status == 401:
                    logger.warning("Token expiré, retry...")
                    continue  # retry avec nouveau token

                if 500 <= response.status < 600:
                    logger.warning(f"Erreur serveur {response.status}, retry {attempt}/{MAX_RETRIES}")
                    await asyncio.sleep(RETRY_DELAY)
                    continue

                response.raise_for_status()
                return await response.json()

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(
                f"Erreur réseau (tentative {attempt}/{MAX_RETRIES}) : {e}"
            )
            await asyncio.sleep(RETRY_DELAY)

    logger.error("Échec définitif de l'envoi de l'événement après retries")
    return False


async def send_plate_event_async(
    session: aiohttp.ClientSession,
    frame: np.ndarray,
    camera_id: int,
    plate_text: str,
    confidence: float,
    vehicle_id: int = None,
    event_type: str = "PLATE_RECOGNITION",
):
    """
    Envoie un événement de reconnaissance de plaque au backend (POST /events/add),
    avec le snapshot et les champs LPR (plate_text_detected, vehicle_id).

    Distinct de send_event_async (facial) pour ne pas modifier le pipeline existant.

    Timeouts courts et propres : l'événement est envoyé depuis un worker découplé
    (jamais sur le chemin critique vidéo) ; en réseau Docker local la latence est
    < 50 ms, donc 5 s de timeout + 2 tentatives suffisent largement. Un échec est
    abandonné sans bloquer (la perte d'un snapshot est tolérable).
    """
    URL = f"{API_URL}/events/add"

    # Constantes LOCALES (n'affectent pas send_event_async / le pipeline facial).
    PLATE_MAX_RETRIES = 2
    PLATE_RETRY_DELAY = 0.5
    PLATE_TIMEOUT = aiohttp.ClientTimeout(total=5)

    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        logger.error("[plate-event] Erreur encodage image")
        return False
    image_bytes = buffer.tobytes()

    for attempt in range(1, PLATE_MAX_RETRIES + 1):
        headers = get_auth_headers()

        form = aiohttp.FormData()
        form.add_field("image", image_bytes, filename="plate_event.jpg", content_type="image/jpeg")
        form.add_field("camera_id", str(camera_id))
        form.add_field("event_type", event_type)
        form.add_field("confidence", str(confidence))
        form.add_field("plate_text_detected", plate_text)
        if vehicle_id is not None:
            form.add_field("vehicle_id", str(vehicle_id))

        try:
            async with session.post(
                URL, data=form, headers=headers, timeout=PLATE_TIMEOUT
            ) as response:
                if response.status == 401:
                    logger.warning("[plate-event] Token expiré, retry...")
                    continue
                if 500 <= response.status < 600:
                    logger.warning(f"[plate-event] Erreur serveur {response.status}, retry {attempt}/{PLATE_MAX_RETRIES}")
                    await asyncio.sleep(PLATE_RETRY_DELAY)
                    continue
                response.raise_for_status()
                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"[plate-event] Erreur réseau (tentative {attempt}/{PLATE_MAX_RETRIES}) : {e}")
            await asyncio.sleep(PLATE_RETRY_DELAY)

    logger.error("[plate-event] Échec définitif de l'envoi de l'événement plaque")
    return False

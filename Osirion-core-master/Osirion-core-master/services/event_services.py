import asyncio
import aiohttp
import cv2
import numpy as np
from typing import Optional
from utils.auth_utils import get_auth_headers, API_URL
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # secondes


async def send_event_async(
    session: aiohttp.ClientSession,
    frame: np.ndarray,
    camera_id: int,
    person_id: Optional[int],
    event_type: str,
    confidence: float
):
    # person_id est OPTIONNEL : None pour un visage non reconnu (event_type=
    # UNKNOWN_FACE). Le champ n'est alors pas posté → le backend enregistre
    # person_id=NULL (la colonne est nullable). Comportement INCHANGÉ pour les
    # appels existants qui passent un entier (reconnaissance faciale standard).
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
        if person_id is not None:
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



# services/plate_search_service.py
"""
Recherche floue d'une plaque côté backend (POST /plates/search).

Symétrique de embeddings_search_service.search_embedding_async (recherche faciale).
Gère le refresh token sur 401 et un backoff léger sur 429/5xx.
"""
import asyncio
import aiohttp
from typing import Optional, Dict

from utils.auth_utils import get_auth_headers, API_URL
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def search_plate_async(
    session: aiohttp.ClientSession,
    plate_text: str,
    threshold: float = 0.82,
    k: int = 1,
) -> Optional[Dict]:
    """
    Interroge /plates/search. Retourne le meilleur match (dict) ou None.

    Réponse backend : { query, matched: bool, results: [ {id, plate_text,
        owner_name, is_blacklisted, score, exact}, ... ] }
    """
    url = f"{API_URL}/plates/search"
    payload = {"plate_text": plate_text, "threshold": threshold, "k": k}

    for attempt in range(1, _MAX_RETRIES + 1):
        headers = get_auth_headers()
        wait = _BACKOFF_BASE * (2 ** (attempt - 1))
        try:
            async with session.post(
                url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    return results[0] if results else None

                if resp.status == 401:
                    refreshed = get_auth_headers(force=True)
                    async with session.post(
                        url, json=payload, headers=refreshed, timeout=_REQUEST_TIMEOUT
                    ) as retry_resp:
                        if retry_resp.status == 200:
                            data = await retry_resp.json()
                            results = data.get("results", [])
                            return results[0] if results else None
                        logger.warning(f"[plate-search] 401 persistant après refresh (HTTP {retry_resp.status})")
                        return None

                if resp.status in (429,) or resp.status >= 500:
                    if attempt < _MAX_RETRIES:
                        logger.warning(f"[plate-search] HTTP {resp.status} — backoff {wait:.1f}s ({attempt}/{_MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    logger.error(f"[plate-search] HTTP {resp.status} persistant — abandon.")
                    return None

                logger.warning(f"[plate-search] HTTP {resp.status} inattendu — abandon.")
                return None

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if attempt < _MAX_RETRIES:
                logger.warning(f"[plate-search] erreur réseau ({e}) — backoff {wait:.1f}s ({attempt}/{_MAX_RETRIES})")
                await asyncio.sleep(wait)
            else:
                logger.error(f"[plate-search] échec réseau définitif : {e}")
                return None
        except Exception as e:
            logger.error(f"[plate-search] exception inattendue : {e}", exc_info=True)
            return None

    return None

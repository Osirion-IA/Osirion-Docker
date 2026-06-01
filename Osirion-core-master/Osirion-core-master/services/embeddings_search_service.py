# services/embeddings_search_service.py
import asyncio
import aiohttp
from utils.auth_utils import get_auth_headers, API_URL
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)

# Politique de retry :
#   - 3 tentatives max (attempt 1 = appel initial, 2-3 = retries)
#   - Backoff exponentiel : 0.5s, 1.0s, 2.0s
#   - Retry sur : erreur réseau, timeout, HTTP 5xx, HTTP 429
#   - Refresh token immédiat sur HTTP 401, puis retry unique
#   - Abandon immédiat sur HTTP 4xx (sauf 401 et 429)
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # secondes
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def search_embedding_async(session: aiohttp.ClientSession, embedding, top_k: int = 1) -> List:
    """
    Recherche asynchrone d'un embedding avec retry + exponential backoff.

    Comportement :
      - HTTP 200 : retourne les résultats
      - HTTP 401 : refresh token + 1 retry immédiat
      - HTTP 429 : backoff exponentiel + retry
      - HTTP 5xx : backoff exponentiel + retry
      - Timeout / réseau : backoff exponentiel + retry
      - HTTP 4xx autres : abandon immédiat (erreur client non-corrigible)
    """
    url = f"{API_URL}/people/search/"
    payload = {
        "embedding": embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding),
        "k": top_k
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        headers = get_auth_headers()
        wait = _BACKOFF_BASE * (2 ** (attempt - 1))  # 0.5s, 1.0s, 2.0s

        try:
            async with session.post(
                url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT
            ) as response:

                if response.status == 200:
                    data = await response.json()
                    return data.get("results", [])

                elif response.status == 401:
                    # Token expiré : refresh immédiat + 1 retry sans backoff
                    logger.debug(f"[search] HTTP 401 — refresh token (attempt {attempt})")
                    refreshed_headers = get_auth_headers()
                    async with session.post(
                        url, json=payload, headers=refreshed_headers, timeout=_REQUEST_TIMEOUT
                    ) as retry_resp:
                        if retry_resp.status == 200:
                            data = await retry_resp.json()
                            return data.get("results", [])
                        logger.warning(
                            f"[search] Toujours 401 après refresh token "
                            f"(HTTP {retry_resp.status}) — abandon."
                        )
                        return []

                elif response.status == 429:
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            f"[search] Rate limit (429) — backoff {wait:.1f}s "
                            f"(attempt {attempt}/{_MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "[search] Rate limit (429) persistant après "
                            f"{_MAX_RETRIES} tentatives — augmenter RATE_LIMIT_GENERAL côté backend."
                        )
                        return []

                elif response.status >= 500:
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            f"[search] Erreur serveur HTTP {response.status} — "
                            f"backoff {wait:.1f}s (attempt {attempt}/{_MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            f"[search] HTTP {response.status} persistant après "
                            f"{_MAX_RETRIES} tentatives."
                        )
                        return []

                else:
                    # 4xx non-géré : erreur client, inutile de réessayer
                    logger.warning(
                        f"[search] HTTP {response.status} inattendu — abandon immédiat."
                    )
                    return []

        except asyncio.TimeoutError:
            if attempt < _MAX_RETRIES:
                logger.warning(
                    f"[search] Timeout (>{_REQUEST_TIMEOUT.total}s) — "
                    f"backoff {wait:.1f}s (attempt {attempt}/{_MAX_RETRIES})"
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"[search] Timeout persistant après {_MAX_RETRIES} tentatives — "
                    "vérifier la connectivité backend."
                )
                return []

        except aiohttp.ClientConnectorError as e:
            if attempt < _MAX_RETRIES:
                logger.warning(
                    f"[search] Erreur connexion : {e} — "
                    f"backoff {wait:.1f}s (attempt {attempt}/{_MAX_RETRIES})"
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"[search] Connexion impossible après {_MAX_RETRIES} tentatives : {e}"
                )
                return []

        except Exception as e:
            # Exception inattendue : logger et abandonner pour ne pas boucler indéfiniment
            logger.error(f"[search] Exception inattendue (attempt {attempt}) : {e}", exc_info=True)
            return []

    return []
# app/services/response_cache.py
"""Cache mémoire à TTL court pour les agrégats analytiques recalculés à la volée.

Les endpoints d'analytique / disponibilité recalculent des agrégats coûteux
depuis la table `event` à CHAQUE appel. Or le Cockpit les interroge toutes les
8 s et plusieurs opérateurs peuvent être connectés simultanément → le même calcul
est refait en boucle. Ce cache process-local (clé = endpoint + paramètres) sert la
même réponse pendant `ttl` secondes : la charge DB devient au pire « 1 recalcul
par fenêtre TTL », quel que soit le nombre de clients. Les chiffres restent quasi
temps réel (retard ≤ TTL).

Volontairement simple et sans dépendance externe (Redis viendra avec la
pré-agrégation) : thread-safe, éviction opportuniste des entrées expirées.
"""
import time
import threading
import functools

_lock = threading.Lock()
_store = {}                      # clé -> (expires_at_monotonic, valeur)
_MAX_ENTRIES = 512


def cache_get_or_set(key, ttl, compute):
    """Retourne la valeur en cache pour `key` si fraîche, sinon calcule via
    `compute()`, la met en cache `ttl` s et la retourne. Le calcul se fait HORS
    verrou (ne bloque pas les autres clés pendant un agrégat lent)."""
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = compute()
    with _lock:
        _store[key] = (now + ttl, value)
        if len(_store) > _MAX_ENTRIES:
            for k in [k for k, (exp, _v) in _store.items() if exp <= now]:
                _store.pop(k, None)
    return value


def invalidate(prefix=None):
    """Purge tout le cache (prefix=None) ou les clés commençant par `prefix`."""
    with _lock:
        if prefix is None:
            _store.clear()
        else:
            for k in [k for k in _store if k.startswith(prefix)]:
                _store.pop(k, None)


def cached_endpoint(prefix, ttl):
    """Décore un endpoint FastAPI SYNCHRONE : met son résultat en cache `ttl` s,
    clé = `prefix` + paramètres de requête (hors `session` / `_user`, qui ne
    changent pas la valeur agrégée — mêmes chiffres pour tous les viewers).

    `functools.wraps` préserve la signature d'origine → l'injection de dépendances
    FastAPI (Query, Depends) reste intacte. Appeler la fonction décorée directement
    (ex. depuis l'endpoint agrégé) réutilise donc le MÊME cache que l'appel HTTP.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            parts = [prefix]
            for k in sorted(kwargs):
                if k in ("session", "_user"):
                    continue
                parts.append(f"{k}={kwargs[k]}")
            return cache_get_or_set("|".join(parts), ttl, lambda: fn(*args, **kwargs))
        return wrapper
    return deco

/**
 * Wrapper fetch avec refresh automatique du token sur 401.
 *
 * - Déduplique les appels concurrents : si plusieurs requêtes expirent en même
 *   temps, un seul appel /api/auth/refresh est lancé ; les autres attendent.
 * - Si le refresh échoue (refresh_token expiré), redirige vers le login.
 * - Retourne null si redirigé (le composant appelant doit vérifier).
 */

let _refreshPromise = null;

function _triggerRefresh() {
  if (!_refreshPromise) {
    _refreshPromise = fetch("/api/auth/refresh", { method: "POST" }).finally(
      () => { _refreshPromise = null; }
    );
  }
  return _refreshPromise;
}

export async function fetchWithRefresh(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status !== 401) return res;

  const refresh = await _triggerRefresh();
  if (!refresh.ok) {
    window.location.href = "/";
    return null;
  }

  return fetch(url, options);
}

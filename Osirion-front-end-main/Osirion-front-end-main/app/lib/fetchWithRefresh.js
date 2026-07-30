/**
 * Wrapper fetch avec refresh automatique du token sur 401.
 *
 * - Déduplique les appels concurrents : un seul /api/auth/refresh à la fois
 *   (`triggerRefresh`), PARTAGÉ avec le refresh proactif du layout → évite qu'un
 *   refresh réactif et un refresh proactif se marchent dessus (le backend fait
 *   TOURNER le refresh_token : deux refresh concurrents invalideraient l'un l'autre).
 * - Filet anti-course (rotation / multi-onglets) : si le refresh échoue, un autre
 *   onglet a peut-être déjà rafraîchi le cookie → on retente la requête une fois
 *   avant d'abandonner. On ne déconnecte que si la session est réellement morte.
 * - Retourne null si redirigé (le composant appelant doit vérifier).
 */

let _refreshPromise = null;

// Un seul refresh en vol à la fois (partagé). Exporté pour que le layout l'utilise
// aussi → un seul point de rafraîchissement dans tout l'onglet.
export function triggerRefresh() {
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

  const refresh = await triggerRefresh();
  if (!refresh.ok) {
    // Le refresh a échoué : peut-être une course (rotation) où un autre refresh a
    // déjà mis à jour le cookie access_token → on retente une fois. Si ça repasse,
    // la session est vivante ; sinon seulement, on déconnecte.
    const retry = await fetch(url, options);
    if (retry.status !== 401) return retry;
    window.location.href = "/";
    return null;
  }

  return fetch(url, options);
}

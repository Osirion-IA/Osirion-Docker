/**
 * URL publiques des services accédés DIRECTEMENT par le navigateur
 * (hors proxy /api same-origin) :
 *   • Core   (Socket.IO + endpoints /api/* du moteur) — port 5000
 *   • MediaMTX (vidéo WebRTC / WHEP)                  — port 8889
 *
 * Problème résolu : ces services écoutent sur des ports distincts du frontend.
 * Si on code "localhost" en dur, un poste distant du réseau tape SON PROPRE
 * localhost → la vidéo et l'overlay temps réel échouent. On dérive donc l'hôte
 * du navigateur courant (window.location.hostname) → ça marche depuis n'importe
 * quel poste du LAN, sans reconfiguration.
 *
 * Ordre de résolution :
 *   1. NEXT_PUBLIC_* explicite ET non-localhost → respectée (override multi-hôtes/HTTPS).
 *   2. Navigateur → protocole + hôte courant + port du service.
 *   3. SSR / repli → localhost (jamais servi tel quel à un navigateur distant).
 */

function isLocalHostUrl(url) {
  return !url || /\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(url);
}

function serviceUrl(envValue, port) {
  // 1. Override explicite (déploiement dédié / HTTPS).
  if (!isLocalHostUrl(envValue)) return envValue;
  // 2. Navigateur : reconstruit l'URL depuis l'hôte réel d'accès.
  if (typeof window !== "undefined" && window.location?.hostname) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${port}`;
  }
  // 3. SSR / repli (non utilisé côté navigateur distant).
  return `http://localhost:${port}`;
}

export const CORE_URL = serviceUrl(process.env.NEXT_PUBLIC_CORE_URL, 5000);
export const SOCKET_URL = serviceUrl(process.env.NEXT_PUBLIC_SOCKET_URL, 5000);
export const MEDIAMTX_URL = serviceUrl(process.env.NEXT_PUBLIC_MEDIAMTX_URL, 8889);

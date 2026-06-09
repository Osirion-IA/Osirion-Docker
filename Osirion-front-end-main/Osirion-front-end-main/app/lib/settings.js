/**
 * Accès aux paramètres persistés localement (page Paramètres → Général/Sécurité).
 * Source unique de vérité pour la clé de stockage, partagée entre la page
 * Paramètres, le layout admin (déconnexion auto) et la création d'utilisateur
 * (longueur de mot de passe).
 */
export const SETTINGS_STORAGE_KEY = "osirion-settings";

export function getSetting(key, fallback = undefined) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return fallback;
    const obj = JSON.parse(raw);
    return obj[key] !== undefined ? obj[key] : fallback;
  } catch {
    return fallback;
  }
}

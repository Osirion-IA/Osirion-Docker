// Vocabulaire COMMUN de l'état d'une caméra.
//
// Trois notions distinctes étaient confondues dans l'interface, toutes rendues
// par « En ligne / Hors ligne » à partir du seul champ `is_active` :
//
//  1. TRAITÉE (`is_active`) — Osirion analyse ce flux. C'est un choix de
//     configuration, pas un état du réseau : une caméra parfaitement joignable
//     mais non configurée est `is_active = false`.
//  2. JOIGNABLE (`hik_status`) — le VMS HikCentral voit la caméra. 1 = oui,
//     2 = non, null = inconnu (caméra RTSP directe, non inventoriée par le VMS).
//  3. FLUX EXPLOITABLE (camera_status_event) — notre relais parvient à tirer et
//     décoder le flux. Une caméra peut être joignable côté VMS et malgré tout
//     inexploitable chez nous (relais en timeout). Cette notion-là vit sur
//     l'écran « Santé caméras », qui ne parle que des caméras traitées.
//
// Afficher (1) sous le libellé (2) revenait à annoncer 113 caméras tombées quand
// 41 seulement l'étaient. Ce module est la source unique des libellés.

export const REACH_ONLINE = "online";
export const REACH_OFFLINE = "offline";
export const REACH_UNKNOWN = "unknown";

/** Joignabilité réelle d'après le VMS — jamais `is_active`. */
export function reachability(camera) {
  if (camera?.hik_status === 1) return REACH_ONLINE;
  if (camera?.hik_status === 2) return REACH_OFFLINE;
  return REACH_UNKNOWN;
}

export const REACH_LABEL = {
  [REACH_ONLINE]: "Joignable",
  [REACH_OFFLINE]: "Injoignable",
  [REACH_UNKNOWN]: "État inconnu",
};

export const REACH_COLOR = {
  [REACH_ONLINE]: "var(--os-green)",
  [REACH_OFFLINE]: "var(--os-red)",
  [REACH_UNKNOWN]: "var(--os-t4)",
};

/** Traitée par le moteur — choix de configuration. */
export const isProcessed = (camera) => !!camera?.is_active;
export const PROCESSED_LABEL = { true: "Traitée", false: "Non traitée" };

/** Compteurs d'un parc : total, traitées, et joignabilité. */
export function fleetCounts(cameras) {
  const list = Array.isArray(cameras) ? cameras : [];
  return {
    total: list.length,
    processed: list.filter(isProcessed).length,
    online: list.filter((c) => reachability(c) === REACH_ONLINE).length,
    offline: list.filter((c) => reachability(c) === REACH_OFFLINE).length,
    unknown: list.filter((c) => reachability(c) === REACH_UNKNOWN).length,
  };
}

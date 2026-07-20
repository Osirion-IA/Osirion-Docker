// Regroupement des caméras par site (groupe), partagé par l'éditeur de Zones et
// la santé des caméras. Le catalogue HikCentral est importé par site : afficher
// les caméras groupées facilite la sélection parmi des dizaines de caméras.

const UNGROUPED = "__ungrouped__";

// cameras: [{ id, cam_name, group_ids, source_type, hik_status, is_active }]
// groups:  [{ id, name }]
// → [{ id, name, cameras: [...] }] trié par nom de site (« Sans site » en dernier),
//   caméras triées par nom. Une caméra multi-groupes apparaît sous chaque site.
export function groupCamerasBySite(cameras, groups) {
  const nameById = new Map((groups || []).map((g) => [g.id, g.name]));
  const buckets = new Map();
  for (const c of cameras || []) {
    const gids = c.group_ids && c.group_ids.length ? c.group_ids : [UNGROUPED];
    for (const gid of gids) {
      if (!buckets.has(gid)) {
        buckets.set(gid, {
          id: gid,
          name: gid === UNGROUPED ? "Sans site" : nameById.get(gid) || `Groupe ${gid}`,
          cameras: [],
        });
      }
      buckets.get(gid).cameras.push(c);
    }
  }
  const arr = [...buckets.values()];
  arr.sort((a, b) => {
    if (a.id === UNGROUPED) return 1;
    if (b.id === UNGROUPED) return -1;
    return a.name.localeCompare(b.name, "fr");
  });
  for (const g of arr) {
    g.cameras.sort((a, b) => (a.cam_name || "").localeCompare(b.cam_name || "", "fr"));
  }
  return arr;
}

// Statut d'affichage d'une caméra du catalogue. Pour HikCentral, on s'appuie sur
// hik_status (1=en ligne, 2=hors-ligne au dernier sync) ; sinon sur is_active.
// Renvoie { tone: "green"|"red"|"muted", label }.
export function catalogStatus(c) {
  if (c.source_type === "hikcentral") {
    if (c.hik_status === 1) return { tone: "green", label: "En ligne" };
    if (c.hik_status === 2) return { tone: "red", label: "Hors ligne" };
    return { tone: "muted", label: "Inconnu" };
  }
  return c.is_active
    ? { tone: "green", label: "Active" }
    : { tone: "muted", label: "Inactive" };
}

export const TONE_COLOR = {
  green: "var(--os-green)",
  red: "var(--os-red)",
  amber: "var(--os-amber)",
  muted: "var(--os-t4)",
};

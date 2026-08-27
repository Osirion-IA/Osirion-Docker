// Export du journal d'événements (CSV / Excel / PDF), partagé. Aucune donnée
// personnelle : ID, date/heure, type, caméra, zone/ligne, sens, valeur.

const COLUMNS = ["ID", "Date", "Heure", "Type", "Caméra", "Zone/Ligne", "Sens", "Valeur"];
const TYPE_LABEL = {
  ZONE_OCCUPANCY_CHANGED: "Occupation", CROWD_DETECTED: "Attroupement",
  LINE_CROSSED: "Franchissement", ZONE_DWELL: "Présence",
  POST_VACANT: "Poste vacant", POST_ABSENCE: "Absence clôturée",
  STAFFING_LOW: "Sous-effectif", STAFFING_RECOVERED: "Effectif rétabli",
  ENTRY: "Entrée", EXIT: "Sortie", DETECTION: "Détection",
};
const dFr = (ts) => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleDateString("fr-FR"); };
const tFr = (ts) => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); };
const dirFr = (dir) => (dir === "in" ? "Entrée" : dir === "out" ? "Sortie" : "—");
const valOf = (m) => (m?.shortage_s != null ? `${Math.round(m.shortage_s)} s de sous-effectif`
  : m?.minimum != null ? `${m.count ?? 0}/${m.maximum} agents · min ${m.minimum}`
  : m?.count != null ? `${m.count} pers.`
  : m?.absence_s != null ? `${Math.round(m.absence_s)} s d'absence`
  : m?.vacant_s != null ? `vide depuis ${Math.round(m.vacant_s)} s`
  : m?.dwell_s != null ? `${Math.round(m.dwell_s)} s` : "—");

function eventToRow(e) {
  const m = e.meta || {};
  return [e.id, dFr(e.timestamp), tFr(e.timestamp), TYPE_LABEL[e.event_type] || e.event_type || "—",
    e.camera_nom || `Caméra ${e.camera_id}`, m.zone_name || m.line_name || "—", dirFr(m.direction), valOf(m)];
}
function stamp() { const d = new Date(), p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`; }
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportCSV(rows, filename) {
  const esc = (v) => { const s = String(v ?? ""); return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const lines = [COLUMNS.map(esc).join(";"), ...rows.map((r) => r.map(esc).join(";"))];
  downloadBlob(new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" }), `${filename}.csv`);
}
function exportExcel(rows, filename, meta) {
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map((h) => `<th style="background:#1c2126;color:#fff;border:1px solid #888;padding:6px 8px;text-align:left;">${escH(h)}</th>`).join("")}</tr>`;
  const tbody = rows.map((r) => `<tr>${r.map((c) => `<td style="border:1px solid #ccc;padding:4px 8px;mso-number-format:'\\@';">${escH(c)}</td>`).join("")}</tr>`).join("");
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="utf-8">` +
    `<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>Journal</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->` +
    `</head><body><p style="font-family:Arial;font-size:13px;"><b>Journal Qwiper Sentinel — ${meta.count} événement(s)</b><br>Généré le ${escH(meta.generatedAt)} — Filtres : ${escH(meta.filters)}</p>` +
    `<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:Arial;font-size:12px;">${thead}${tbody}</table></body></html>`;
  downloadBlob(new Blob(["\ufeff" + html], { type: "application/vnd.ms-excel;charset=utf-8;" }), `${filename}.xls`);
}
function exportPDF(rows, meta) {
  const w = window.open("", "_blank");
  if (!w) { alert("Autorisez les pop-ups pour générer le PDF."); return; }
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map((h) => `<th>${escH(h)}</th>`).join("")}</tr>`;
  const tbody = rows.length ? rows.map((r) => `<tr>${r.map((c) => `<td>${escH(c)}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${COLUMNS.length}" style="text-align:center;color:#888;">Aucun événement</td></tr>`;
  w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Journal Qwiper Sentinel</title><style>
    body{font-family:Arial,sans-serif;color:#111;margin:24px;} header{display:flex;justify-content:space-between;border-bottom:2px solid #1c2126;padding-bottom:12px;margin-bottom:16px;}
    h1{font-size:20px;margin:0 0 4px;} .meta{font-size:12px;color:#555;} .brand{font-size:13px;font-weight:bold;letter-spacing:2px;color:#1c2126;}
    table{width:100%;border-collapse:collapse;font-size:11px;} th{background:#1c2126;color:#fff;text-align:left;padding:6px 8px;} td{border-bottom:1px solid #e5e7eb;padding:5px 8px;}
    tr:nth-child(even) td{background:#f8fafc;} @media print{body{margin:12mm;} @page{size:A4 landscape;}}
    </style></head><body><header><div><h1>Journal d'événements — flux anonymes</h1><div class="meta">Généré le ${escH(meta.generatedAt)}</div><div class="meta">Filtres : ${escH(meta.filters)}</div><div class="meta"><b>${meta.count}</b> événement(s)</div></div><div class="brand">QWIPER SENTINEL</div></header><table><thead>${thead}</thead><tbody>${tbody}</tbody></table></body></html>`);
  w.document.close();
  setTimeout(() => { try { w.focus(); w.print(); } catch { /* */ } }, 300);
}

// Point d'entrée : exporte `events` (déjà filtrés) au format demandé.
export function exportEvents(kind, events, meta) {
  const rows = events.map(eventToRow);
  const filename = `qwiper-sentinel-journal-${stamp()}`;
  if (kind === "csv") exportCSV(rows, filename);
  else if (kind === "excel") exportExcel(rows, filename, meta);
  else if (kind === "pdf") exportPDF(rows, meta);
}

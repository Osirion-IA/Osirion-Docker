"use client";

/**
 * Rapports — exports de flux ANONYMES (section Analyser, thème clair).
 * Aucune donnée personnelle : ID, date/heure, type, caméra, zone/ligne, sens, valeur.
 * Exports CSV / Excel / PDF auto-contenus (offline, sans dépendance).
 */
import { useState, useMemo, useEffect, useCallback } from "react";
import { Download, FileSpreadsheet, FileText, FileType2, ListOrdered } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, RefreshButton, EmptyState } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const TYPE_LABEL = {
  ZONE_OCCUPANCY_CHANGED: "Occupation", CROWD_DETECTED: "Attroupement",
  LINE_CROSSED: "Franchissement", ZONE_DWELL: "Présence",
  ENTRY: "Entrée", EXIT: "Sortie", DETECTION: "Détection",
};
const COLUMNS = ["ID", "Date", "Heure", "Type", "Caméra", "Zone/Ligne", "Sens", "Valeur"];

const fmtDate = (ts) => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleDateString("fr-FR"); };
const fmtTime = (ts) => { const d = new Date(ts); return isNaN(d) ? "" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); };
const dirFr = (dir) => (dir === "in" ? "Entrée" : dir === "out" ? "Sortie" : "—");
const valOf = (m) => (m?.count != null ? `${m.count} pers.` : m?.dwell_s != null ? `${Math.round(m.dwell_s)} s` : "—");

function eventToRow(e) {
  const m = e.meta || {};
  return [
    e.id, fmtDate(e.timestamp), fmtTime(e.timestamp),
    TYPE_LABEL[e.event_type] || e.event_type || "—",
    e.camera_nom || `Caméra ${e.camera_id}`,
    m.zone_name || m.line_name || "—", dirFr(m.direction), valOf(m),
  ];
}
function stamp() {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportCSV(rows, filename) {
  const esc = (v) => { const s = String(v ?? ""); return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const lines = [COLUMNS.map(esc).join(";"), ...rows.map((r) => r.map(esc).join(";"))];
  downloadBlob(new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" }), `${filename}.csv`);
}
function exportExcel(rows, filename, meta) {
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map((h) => `<th style="background:#1c2126;color:#fff;border:1px solid #888;padding:6px 8px;text-align:left;">${escH(h)}</th>`).join("")}</tr>`;
  const tbody = rows.map((r) => `<tr>${r.map((c) => `<td style="border:1px solid #ccc;padding:4px 8px;mso-number-format:'\\@';">${escH(c)}</td>`).join("")}</tr>`).join("");
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="utf-8">` +
    `<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>Rapport</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->` +
    `</head><body><p style="font-family:Arial;font-size:13px;"><b>Rapport Qwiper Sentinel — ${meta.count} événement(s)</b><br>Généré le ${escH(meta.generatedAt)} — Filtres : ${escH(meta.filters)}</p>` +
    `<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:Arial;font-size:12px;">${thead}${tbody}</table></body></html>`;
  downloadBlob(new Blob(["﻿" + html], { type: "application/vnd.ms-excel;charset=utf-8;" }), `${filename}.xls`);
}
function exportPDF(rows, meta) {
  const w = window.open("", "_blank");
  if (!w) { alert("Autorisez les pop-ups pour générer le PDF."); return; }
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map((h) => `<th>${escH(h)}</th>`).join("")}</tr>`;
  const tbody = rows.length
    ? rows.map((r) => `<tr>${r.map((c) => `<td>${escH(c)}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${COLUMNS.length}" style="text-align:center;color:#888;">Aucun événement</td></tr>`;
  w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Rapport Qwiper Sentinel</title><style>
    body{font-family:Arial,sans-serif;color:#111;margin:24px;} header{display:flex;justify-content:space-between;border-bottom:2px solid #1c2126;padding-bottom:12px;margin-bottom:16px;}
    h1{font-size:20px;margin:0 0 4px;} .meta{font-size:12px;color:#555;} .brand{font-size:13px;font-weight:bold;letter-spacing:2px;color:#1c2126;}
    table{width:100%;border-collapse:collapse;font-size:11px;} th{background:#1c2126;color:#fff;text-align:left;padding:6px 8px;} td{border-bottom:1px solid #e5e7eb;padding:5px 8px;}
    tr:nth-child(even) td{background:#f8fafc;} @media print{body{margin:12mm;} @page{size:A4 landscape;}}
    </style></head><body><header><div><h1>Rapport d'événements — flux anonymes</h1><div class="meta">Généré le ${escH(meta.generatedAt)}</div><div class="meta">Filtres : ${escH(meta.filters)}</div><div class="meta"><b>${meta.count}</b> événement(s)</div></div><div class="brand">QWIPER SENTINEL</div></header><table><thead>${thead}</thead><tbody>${tbody}</tbody></table></body></html>`);
  w.document.close();
  setTimeout(() => { try { w.focus(); w.print(); } catch { /* */ } }, 300);
}

export default function ReportsPage() {
  const user = useAuth();
  const canExport = ["admin", "user"].includes(user?.role);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("tous");
  const [cameraFilter, setCameraFilter] = useState("tous");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithRefresh("/api/events?limit=1000");
      const data = res && res.ok ? await res.json() : [];
      setEvents(Array.isArray(data) ? data : []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const cameras = useMemo(() => {
    const m = new Map();
    for (const e of events) if (!m.has(e.camera_id)) m.set(e.camera_id, e.camera_nom || `Caméra ${e.camera_id}`);
    return Array.from(m, ([id, name]) => ({ id, name }));
  }, [events]);

  const filtered = useMemo(() => events.filter((e) => {
    if (typeFilter !== "tous" && e.event_type !== typeFilter) return false;
    if (cameraFilter !== "tous" && String(e.camera_id) !== String(cameraFilter)) return false;
    return true;
  }), [events, typeFilter, cameraFilter]);

  const buildMeta = useCallback(() => {
    const parts = [];
    if (typeFilter !== "tous") parts.push(`type : ${TYPE_LABEL[typeFilter] || typeFilter}`);
    if (cameraFilter !== "tous") parts.push(`caméra : ${cameras.find((c) => String(c.id) === String(cameraFilter))?.name || cameraFilter}`);
    return { generatedAt: new Date().toLocaleString("fr-FR"), filters: parts.length ? parts.join(" · ") : "Aucun (toutes les données)", count: filtered.length };
  }, [typeFilter, cameraFilter, cameras, filtered.length]);

  const doExport = (kind) => {
    if (!filtered.length) return;
    const rows = filtered.map(eventToRow);
    const filename = `qwiper-sentinel-rapport-${stamp()}`;
    const meta = buildMeta();
    if (kind === "csv") exportCSV(rows, filename);
    else if (kind === "excel") exportExcel(rows, filename, meta);
    else if (kind === "pdf") exportPDF(rows, meta);
  };

  const selectCls = "rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none focus:border-os-t3";
  const disabled = loading || filtered.length === 0 || !canExport;
  const btn = "px-3.5 py-2 rounded-os text-[13px] font-semibold inline-flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Rapports"
          subtitle="Exports de flux anonymes · aucune donnée personnelle"
          actions={<RefreshButton onClick={load} spinning={loading} />}
        />

        <Card className="p-5 mb-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="h-10 w-10 grid place-items-center rounded-os bg-os-cta text-white"><Download className="h-5 w-5" /></span>
              <div>
                <h3 className="text-[15px] font-semibold text-os-t1">Exporter le rapport</h3>
                <p className="os-num text-[12px] text-os-t3">{filtered.length} / {events.length} événement(s) selon les filtres</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => doExport("excel")} disabled={disabled} className={`${btn} bg-os-cta text-white hover:bg-os-cta-hover`}><FileSpreadsheet className="h-4 w-4" /> Excel</button>
              <button onClick={() => doExport("pdf")} disabled={disabled} className={`${btn} bg-os-cta text-white hover:bg-os-cta-hover`}><FileText className="h-4 w-4" /> PDF</button>
              <button onClick={() => doExport("csv")} disabled={disabled} className={`${btn} border border-os-border text-os-t2 hover:text-os-t1`}><FileType2 className="h-4 w-4" /> CSV</button>
            </div>
          </div>
          {!canExport && <p className="text-[12px] text-os-amber mt-3">Export réservé aux rôles administrateur / opérateur.</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={selectCls}>
              <option value="tous">Tous les types</option>
              {Object.entries(TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)} className={selectCls}>
              <option value="tous">Toutes les caméras</option>
              {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </Card>

        <Card className="overflow-hidden">
          {loading ? (
            <EmptyState icon={ListOrdered}>Chargement…</EmptyState>
          ) : filtered.length === 0 ? (
            <EmptyState icon={ListOrdered}>{events.length === 0 ? "Aucun événement enregistré." : "Aucun événement ne correspond aux filtres."}</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-os-t3 border-b border-os-border">
                    {COLUMNS.map((c) => <th key={c} className="px-4 py-3 font-semibold whitespace-nowrap">{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 200).map((e) => (
                    <tr key={e.id} className="border-b border-os-border last:border-0">
                      {eventToRow(e).map((cell, i) => (
                        <td key={i} className={`px-4 py-2.5 whitespace-nowrap ${i === 0 || i >= 6 ? "os-num" : ""} ${i === 0 ? "text-os-t3" : "text-os-t2"}`}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length > 200 && <p className="os-num text-[11px] text-os-t4 px-4 py-2 border-t border-os-border">Aperçu limité à 200 lignes · l&apos;export contient les {filtered.length}.</p>}
            </div>
          )}
        </Card>
      </div>
    </OsShell>
  );
}

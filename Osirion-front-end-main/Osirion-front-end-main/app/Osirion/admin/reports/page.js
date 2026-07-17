"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

// ── Icônes SVG inline (mêmes que le style AdminSidebar) ─────────────────────
// Volontairement sans lucide-react ici : auto-contenu, aucun risque de nom
// d'icône inexistant au build. Chaque composant accepte `className`.
const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const Download = ({ className }) => (<Svg className={className}><path d="M12 3v12" /><path d="m7 12 5 5 5-5" /><path d="M5 21h14" /></Svg>);
const FileSpreadsheet = ({ className }) => (<Svg className={className}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M8 13h8M8 17h8M12 13v4" /></Svg>);
const FileText = ({ className }) => (<Svg className={className}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M9 13h6M9 17h4" /></Svg>);
const FileType2 = ({ className }) => (<Svg className={className}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></Svg>);
const Filter = ({ className }) => (<Svg className={className}><path d="M3 4h18l-7 8v6l-4 2v-8z" /></Svg>);
const RefreshCw = ({ className }) => (<Svg className={className}><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" /></Svg>);
const Search = ({ className }) => (<Svg className={className}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></Svg>);
const Calendar = ({ className }) => (<Svg className={className}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></Svg>);
const Inbox = ({ className }) => (<Svg className={className}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5 5h14l3 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6z" /></Svg>);
const BarChart3 = ({ className }) => (<Svg className={className}><path d="M3 3v18h18" /><path d="M7 16v-5M12 16V8M17 16v-3" /></Svg>);
const X = ({ className }) => (<Svg className={className}><path d="M18 6 6 18M6 6l12 12" /></Svg>);

// ── Types d'événements : libellé FR + classes de badge ──────────────────────
// Aligné sur backend app/models/events.py (RECOGNITION, UNKNOWN_FACE,
// ENTRY, EXIT, DETECTION).
const EVENT_TYPES = [
  { value: "RECOGNITION",       label: "Reconnaissance", badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" },
  { value: "UNKNOWN_FACE",      label: "Visage inconnu", badge: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300" },
  { value: "ENTRY",             label: "Entrée",         badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
  { value: "EXIT",              label: "Sortie",         badge: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300" },
  { value: "DETECTION",         label: "Détection",      badge: "bg-gray-200 text-gray-700 dark:bg-gray-700/50 dark:text-gray-300" },
];
const TYPE_LABEL = Object.fromEntries(EVENT_TYPES.map((t) => [t.value, t.label]));
const TYPE_BADGE = Object.fromEntries(EVENT_TYPES.map((t) => [t.value, t.badge]));

// En-têtes de colonnes utilisées dans la table ET dans tous les exports.
const COLUMNS = ["ID", "Date", "Heure", "Type", "Caméra", "Lieu", "Personne", "Confiance"];

// ── Helpers de formatage ────────────────────────────────────────────────────
function fmtDate(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "";
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function fmtTime(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function eventToRow(e) {
  return [
    e.id,
    fmtDate(e.timestamp),
    fmtTime(e.timestamp),
    TYPE_LABEL[e.event_type] || e.event_type || "—",
    e.camera_nom || `CAM-${e.camera_id}`,
    e.camera_location || "—",
    e.person_nom || "—",
    e.confidence != null ? `${Math.round(e.confidence * 100)}%` : "—",
  ];
}
function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

// ── Téléchargement d'un Blob ────────────────────────────────────────────────
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Export CSV (séparateur ';' + BOM UTF-8 → Excel FR ouvre proprement) ──────
function exportCSV(rows, filename) {
  const esc = (v) => {
    const s = String(v ?? "");
    return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const sep = ";";
  const lines = [COLUMNS.map(esc).join(sep), ...rows.map((r) => r.map(esc).join(sep))];
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  downloadBlob(blob, `${filename}.csv`);
}

// ── Export Excel (.xls) — table HTML + namespace MSO, sans dépendance ────────
// Excel/LibreOffice ouvrent nativement ce format en feuille de calcul. Le format
// texte (mso-number-format) évite que les plaques/ID soient réinterprétés.
function exportExcel(rows, filename, meta) {
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map(
    (h) => `<th style="background:#1f2937;color:#ffffff;border:1px solid #888;padding:6px 8px;font-weight:bold;text-align:left;">${escH(h)}</th>`
  ).join("")}</tr>`;
  const tbody = rows.map(
    (r) => `<tr>${r.map(
      (c) => `<td style="border:1px solid #cccccc;padding:4px 8px;mso-number-format:'\\@';">${escH(c)}</td>`
    ).join("")}</tr>`
  ).join("");
  const title = `Rapport Osirion — ${meta.count} événement(s)`;
  const html =
    `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">` +
    `<head><meta charset="utf-8">` +
    `<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet>` +
    `<x:Name>Rapport</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions>` +
    `</x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->` +
    `</head><body>` +
    `<p style="font-family:Arial;font-size:14px;"><b>${escH(title)}</b><br>` +
    `Généré le ${escH(meta.generatedAt)} — Filtres : ${escH(meta.filters)}</p>` +
    `<table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:Arial;font-size:12px;">${thead}${tbody}</table>` +
    `</body></html>`;
  const blob = new Blob(["﻿" + html], { type: "application/vnd.ms-excel;charset=utf-8;" });
  downloadBlob(blob, `${filename}.xls`);
}

// ── Export PDF — fenêtre stylée + impression navigateur (« Enregistrer en PDF »)
function exportPDF(rows, meta) {
  const w = window.open("", "_blank");
  if (!w) {
    alert("Veuillez autoriser les fenêtres pop-up pour générer le PDF.");
    return;
  }
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const thead = `<tr>${COLUMNS.map((h) => `<th>${escH(h)}</th>`).join("")}</tr>`;
  const tbody = rows.length
    ? rows.map((r) => `<tr>${r.map((c) => `<td>${escH(c)}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${COLUMNS.length}" style="text-align:center;color:#888;">Aucun événement</td></tr>`;
  const doc =
    `<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Rapport Osirion</title><style>
      * { box-sizing: border-box; }
      body { font-family: Arial, Helvetica, sans-serif; color:#111; margin:24px; }
      header { display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #1f2937; padding-bottom:12px; margin-bottom:16px; }
      h1 { font-size:20px; margin:0 0 4px; }
      .meta { font-size:12px; color:#555; }
      .brand { font-size:13px; font-weight:bold; letter-spacing:1px; color:#1f2937; }
      table { width:100%; border-collapse:collapse; font-size:11px; }
      th { background:#1f2937; color:#fff; text-align:left; padding:6px 8px; }
      td { border-bottom:1px solid #e5e7eb; padding:5px 8px; }
      tr:nth-child(even) td { background:#f8fafc; }
      footer { margin-top:18px; font-size:10px; color:#888; text-align:right; }
      @media print { body { margin:12mm; } @page { size: A4 landscape; } }
    </style></head><body>
      <header>
        <div>
          <h1>Rapport d'événements</h1>
          <div class="meta">Généré le ${escH(meta.generatedAt)}</div>
          <div class="meta">Filtres : ${escH(meta.filters)}</div>
          <div class="meta"><b>${meta.count}</b> événement(s)</div>
        </div>
        <div class="brand">OSIRION</div>
      </header>
      <table><thead>${thead}</thead><tbody>${tbody}</tbody></table>
      <footer>Osirion — Système de surveillance · ${escH(meta.generatedAt)}</footer>
    </body></html>`;
  w.document.open();
  w.document.write(doc);
  w.document.close();
  // Laisser le rendu se faire avant d'ouvrir la boîte d'impression.
  setTimeout(() => { try { w.focus(); w.print(); } catch { /* ignore */ } }, 300);
}

export default function ReportsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  // Filtres
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [typeFilter, setTypeFilter] = useState("tous");
  const [cameraFilter, setCameraFilter] = useState("tous");
  const [search, setSearch] = useState("");

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const res = await fetchWithRefresh("/api/events?limit=1000");
      if (!res) return;
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFetchError(d?.message || "Erreur de chargement des événements.");
        return;
      }
      const data = await res.json();
      setEvents(Array.isArray(data) ? data : []);
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  // Liste des caméras présentes dans les données (pour le filtre).
  const cameras = useMemo(() => {
    const map = new Map();
    for (const e of events) {
      if (!map.has(e.camera_id)) {
        map.set(e.camera_id, e.camera_nom || `CAM-${e.camera_id}`);
      }
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [events]);

  // Application des filtres.
  const filtered = useMemo(() => {
    const fromTs = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : null;
    const toTs = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : null;
    const q = search.trim().toLowerCase();

    return events.filter((e) => {
      const ts = new Date(e.timestamp).getTime();
      if (fromTs !== null && ts < fromTs) return false;
      if (toTs !== null && ts > toTs) return false;
      if (typeFilter !== "tous" && e.event_type !== typeFilter) return false;
      if (cameraFilter !== "tous" && String(e.camera_id) !== String(cameraFilter)) return false;
      if (q) {
        const hay = [
          e.event_type, e.camera_nom, e.camera_location,
          e.person_nom,
        ].filter(Boolean).join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [events, dateFrom, dateTo, typeFilter, cameraFilter, search]);

  // Stats résumées par type (sur l'ensemble filtré).
  const stats = useMemo(() => {
    const counts = {};
    for (const e of filtered) counts[e.event_type] = (counts[e.event_type] || 0) + 1;
    return counts;
  }, [filtered]);

  const hasFilters = dateFrom || dateTo || typeFilter !== "tous" || cameraFilter !== "tous" || search;
  const resetFilters = () => {
    setDateFrom(""); setDateTo(""); setTypeFilter("tous"); setCameraFilter("tous"); setSearch("");
  };

  // Métadonnées partagées par les exports (résumé des filtres actifs).
  const buildMeta = useCallback(() => {
    const parts = [];
    if (dateFrom) parts.push(`du ${dateFrom}`);
    if (dateTo) parts.push(`au ${dateTo}`);
    if (typeFilter !== "tous") parts.push(`type : ${TYPE_LABEL[typeFilter] || typeFilter}`);
    if (cameraFilter !== "tous") {
      parts.push(`caméra : ${cameras.find((c) => String(c.id) === String(cameraFilter))?.name || cameraFilter}`);
    }
    if (search.trim()) parts.push(`recherche : "${search.trim()}"`);
    return {
      generatedAt: new Date().toLocaleString("fr-FR"),
      filters: parts.length ? parts.join(" · ") : "Aucun (toutes les données)",
      count: filtered.length,
    };
  }, [dateFrom, dateTo, typeFilter, cameraFilter, search, cameras, filtered.length]);

  const doExport = (kind) => {
    if (!filtered.length) return;
    const rows = filtered.map(eventToRow);
    const filename = `osirion-rapport-${stamp()}`;
    const meta = buildMeta();
    if (kind === "csv") exportCSV(rows, filename);
    else if (kind === "excel") exportExcel(rows, filename, meta);
    else if (kind === "pdf") exportPDF(rows, meta);
  };

  // Garde de rôle : Rapports réservé aux admin/user (cf. AdminSidebar).
  if (user && !["admin", "user"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/reports" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  const exportDisabled = loading || filtered.length === 0;

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/reports"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Rapports"
            subtitle="Générer et exporter des rapports d'événements"
            showSearch={false}
            actions={
              <button
                onClick={loadEvents}
                className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                Actualiser
              </button>
            }
          />

          <div className="p-6 space-y-6">
            {/* ── Barre d'export ── */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white">
                    <Download className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-gray-900 dark:text-white">Exporter le rapport</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {filtered.length} événement(s) sur {events.length} — selon les filtres actifs
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => doExport("excel")}
                    disabled={exportDisabled}
                    className="rounded-xl px-4 py-2.5 text-sm font-semibold flex items-center gap-2 transition-all bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <FileSpreadsheet className="h-4 w-4" /> Excel
                  </button>
                  <button
                    onClick={() => doExport("pdf")}
                    disabled={exportDisabled}
                    className="rounded-xl px-4 py-2.5 text-sm font-semibold flex items-center gap-2 transition-all bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <FileText className="h-4 w-4" /> PDF
                  </button>
                  <button
                    onClick={() => doExport("csv")}
                    disabled={exportDisabled}
                    className="rounded-xl px-4 py-2.5 text-sm font-semibold flex items-center gap-2 transition-all border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <FileType2 className="h-4 w-4" /> CSV
                  </button>
                </div>
              </div>
            </div>

            {/* ── Filtres ── */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
              <div className="flex items-center gap-2 mb-4">
                <Filter className="h-4 w-4 text-gray-500" />
                <h3 className="text-sm font-bold text-gray-900 dark:text-white">Filtres</h3>
                {hasFilters && (
                  <button
                    onClick={resetFilters}
                    className="ml-auto text-xs font-medium text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 flex items-center gap-1"
                  >
                    <X className="h-3.5 w-3.5" /> Réinitialiser
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" /> Du
                  </label>
                  <input
                    type="date"
                    value={dateFrom}
                    max={dateTo || undefined}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" /> Au
                  </label>
                  <input
                    type="date"
                    value={dateTo}
                    min={dateFrom || undefined}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Type d&apos;événement</label>
                  <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="tous">Tous les types</option>
                    {EVENT_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Caméra</label>
                  <select
                    value={cameraFilter}
                    onChange={(e) => setCameraFilter(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="tous">Toutes les caméras</option>
                    {cameras.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Recherche</label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Personne, lieu..."
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 pl-9 pr-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* ── Stats résumées ── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs font-medium">
                  <BarChart3 className="h-3.5 w-3.5" /> Total
                </div>
                <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{filtered.length}</div>
              </div>
              {EVENT_TYPES.map((t) => (
                <div key={t.value} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400 truncate">{t.label}</div>
                  <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{stats[t.value] || 0}</div>
                </div>
              ))}
            </div>

            {/* ── Tableau ── */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
              {fetchError ? (
                <div className="p-10 text-center">
                  <p className="text-sm text-rose-600 dark:text-rose-400">{fetchError}</p>
                  <button onClick={loadEvents} className="mt-3 text-sm font-medium text-indigo-600 hover:underline">Réessayer</button>
                </div>
              ) : loading ? (
                <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
                  <RefreshCw className="h-6 w-6 mx-auto mb-3 animate-spin opacity-60" />
                  Chargement des événements…
                </div>
              ) : filtered.length === 0 ? (
                <div className="p-12 text-center">
                  <Inbox className="h-10 w-10 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {events.length === 0 ? "Aucun événement enregistré." : "Aucun événement ne correspond aux filtres."}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 dark:bg-gray-800/50 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                        <th className="px-4 py-3">Date / Heure</th>
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3">Caméra</th>
                        <th className="px-4 py-3">Lieu</th>
                        <th className="px-4 py-3">Personne</th>
                        <th className="px-4 py-3">Confiance</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {filtered.map((e) => (
                        <tr key={e.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors">
                          <td className="px-4 py-3 whitespace-nowrap">
                            <div className="font-medium text-gray-900 dark:text-white">{fmtDate(e.timestamp)}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">{fmtTime(e.timestamp)}</div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${TYPE_BADGE[e.event_type] || "bg-gray-200 text-gray-700 dark:bg-gray-700/50 dark:text-gray-300"}`}>
                              {TYPE_LABEL[e.event_type] || e.event_type}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{e.camera_nom || `CAM-${e.camera_id}`}</td>
                          <td className="px-4 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">{e.camera_location || "—"}</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{e.person_nom || "—"}</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{e.confidence != null ? `${Math.round(e.confidence * 100)}%` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

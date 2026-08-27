"use client";

/**
 * Événements — journal de comptage ANONYME (section Analyser, thème clair).
 * Aucune identité : type, sens, caméra, zone/ligne, valeur. Données /api/events.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { ListOrdered, FileSpreadsheet, FileText, FileType2 } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, RefreshButton, EmptyState } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { exportEvents } from "../../../lib/eventExport";

// Type d'événement → libellé FR + couleur du point (rouge = anomalie uniquement).
const TYPE_META = {
  ZONE_OCCUPANCY_CHANGED: { label: "Occupation", color: "var(--os-blue)" },
  CROWD_DETECTED: { label: "Attroupement", color: "var(--os-red)" },
  LINE_CROSSED: { label: "Franchissement", color: "var(--os-amber)" },
  ZONE_DWELL: { label: "Présence", color: "var(--os-blue)" },
  POST_VACANT: { label: "Poste vacant", color: "var(--os-red)" },
  POST_ABSENCE: { label: "Absence clôturée", color: "var(--os-amber)" },
  STAFFING_LOW: { label: "Sous-effectif", color: "var(--os-red)" },
  STAFFING_RECOVERED: { label: "Effectif rétabli", color: "var(--os-green)" },
  ENTRY: { label: "Entrée", color: "var(--os-t4)" },
  EXIT: { label: "Sortie", color: "var(--os-t4)" },
  DETECTION: { label: "Détection", color: "var(--os-t4)" },
};

function fmtTime(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "—";
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
const dirFr = (dir) => (dir === "in" ? "Entrée" : dir === "out" ? "Sortie" : "—");

export default function EventsPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("tous");
  const [cameraFilter, setCameraFilter] = useState("tous");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithRefresh("/api/events?limit=500");
      const data = res && res.ok ? await res.json() : [];
      setEvents(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const cameras = useMemo(() => {
    const m = new Map();
    for (const e of events) if (!m.has(e.camera_id)) m.set(e.camera_id, e.camera_nom || `Caméra ${e.camera_id}`);
    return Array.from(m, ([id, name]) => ({ id, name }));
  }, [events]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return events.filter((e) => {
      if (typeFilter !== "tous" && e.event_type !== typeFilter) return false;
      if (cameraFilter !== "tous" && String(e.camera_id) !== String(cameraFilter)) return false;
      if (q) {
        const hay = [e.event_type, e.camera_nom, e.camera_location, e.meta?.zone_name, e.meta?.line_name].filter(Boolean).join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [events, typeFilter, cameraFilter, search]);

  const user = useAuth();
  const canExport = ["admin", "user"].includes(user?.role || "viewer");
  const doExport = (kind) => {
    if (!filtered.length) return;
    const parts = [];
    if (typeFilter !== "tous") parts.push(`type : ${TYPE_META[typeFilter]?.label || typeFilter}`);
    if (cameraFilter !== "tous") parts.push(`caméra : ${cameras.find((c) => String(c.id) === String(cameraFilter))?.name || cameraFilter}`);
    if (search.trim()) parts.push(`recherche : ${search.trim()}`);
    exportEvents(kind, filtered, { generatedAt: new Date().toLocaleString("fr-FR"), filters: parts.length ? parts.join(" · ") : "Aucun", count: filtered.length });
  };

  const selectCls = "rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none focus:border-os-t3";
  const btn = "px-3 py-2 rounded-os text-[13px] font-semibold inline-flex items-center gap-2 disabled:opacity-40";

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Événements"
          subtitle={`${filtered.length} événement(s) · journal de comptage anonyme`}
          actions={<RefreshButton onClick={load} spinning={loading} />}
        />

        <Card className="p-4 mb-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={selectCls}>
              <option value="tous">Tous les types</option>
              {Object.entries(TYPE_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
            </select>
            <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)} className={selectCls}>
              <option value="tous">Toutes les caméras</option>
              {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <input
              type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Zone, caméra, lieu…" className={selectCls}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-os-border pt-3">
            <span className="os-num text-[12px] text-os-t3">{filtered.length} / {events.length} événement(s){!canExport ? " · export réservé admin/opérateur" : ""}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => doExport("excel")} disabled={!filtered.length || !canExport} className={`${btn} bg-os-cta text-white hover:bg-os-cta-hover`}><FileSpreadsheet className="h-4 w-4" /> Excel</button>
              <button onClick={() => doExport("pdf")} disabled={!filtered.length || !canExport} className={`${btn} bg-os-cta text-white hover:bg-os-cta-hover`}><FileText className="h-4 w-4" /> PDF</button>
              <button onClick={() => doExport("csv")} disabled={!filtered.length || !canExport} className={`${btn} border border-os-border text-os-t2 hover:text-os-t1`}><FileType2 className="h-4 w-4" /> CSV</button>
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          {loading ? (
            <EmptyState icon={ListOrdered}>Chargement…</EmptyState>
          ) : filtered.length === 0 ? (
            <EmptyState icon={ListOrdered}>
              {events.length === 0 ? "Aucun événement enregistré." : "Aucun événement ne correspond aux filtres."}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-os-t3 border-b border-os-border">
                    <th className="px-4 py-3 font-semibold">Heure</th>
                    <th className="px-4 py-3 font-semibold">Type</th>
                    <th className="px-4 py-3 font-semibold">Caméra</th>
                    <th className="px-4 py-3 font-semibold">Zone / Ligne</th>
                    <th className="px-4 py-3 font-semibold">Sens</th>
                    <th className="px-4 py-3 font-semibold text-right">Valeur</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((e) => {
                    const meta = TYPE_META[e.event_type] || { label: e.event_type, color: "var(--os-t4)" };
                    const m = e.meta || {};
                    const value = m.shortage_s != null ? `${Math.round(m.shortage_s)} s de sous-effectif`
                      : m.minimum != null ? `${m.count ?? 0}/${m.maximum} agents · min ${m.minimum}`
                      : m.count != null ? `${m.count} pers.`
                      : m.absence_s != null ? `${Math.round(m.absence_s)} s d'absence`
                      : m.vacant_s != null ? `vide depuis ${Math.round(m.vacant_s)} s`
                      : m.dwell_s != null ? `${Math.round(m.dwell_s)} s` : "—";
                    return (
                      <tr key={e.id} className="border-b border-os-border last:border-0 hover:bg-black/[0.015] dark:hover:bg-white/[0.02]">
                        <td className="px-4 py-3 os-num text-os-t2 whitespace-nowrap">{fmtTime(e.timestamp)}</td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-1.5 text-os-t1 font-medium">
                            <span className="h-2 w-2 rounded-full" style={{ background: meta.color }} />{meta.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-os-t2 whitespace-nowrap">{e.camera_nom || `Caméra ${e.camera_id}`}</td>
                        <td className="px-4 py-3 text-os-t2">{m.zone_name || m.line_name || "—"}</td>
                        <td className="px-4 py-3 text-os-t2">{dirFr(m.direction)}</td>
                        <td className="px-4 py-3 os-num text-os-t1 text-right whitespace-nowrap">{value}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </OsShell>
  );
}

"use client";

/**
 * Événements — journal de comptage ANONYME (section Analyser, thème clair).
 * Aucune identité : type, sens, caméra, zone/ligne, valeur. Données /api/events.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { ListOrdered } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, RefreshButton, EmptyState } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

// Type d'événement → libellé FR + couleur du point (rouge = anomalie uniquement).
const TYPE_META = {
  ZONE_OCCUPANCY_CHANGED: { label: "Occupation", color: "var(--os-blue)" },
  CROWD_DETECTED: { label: "Attroupement", color: "var(--os-red)" },
  LINE_CROSSED: { label: "Franchissement", color: "var(--os-amber)" },
  ZONE_DWELL: { label: "Présence", color: "var(--os-blue)" },
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

  const selectCls = "rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none focus:border-os-t3";

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
                    const value = m.count != null ? `${m.count} pers.` : m.dwell_s != null ? `${Math.round(m.dwell_s)} s` : "—";
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

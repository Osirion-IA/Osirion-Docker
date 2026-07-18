"use client";

/**
 * Dashboard Analytics — fréquentation, occupation, files d'attente.
 * Agrégats calculés côté backend (/analytics/*) à partir des événements de
 * l'Event Engine. Graphiques custom SVG/CSS (aucune dépendance ajoutée).
 */
import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

function fmtWait(s) {
  if (!s) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

// Graphe à barres groupées entrées/sorties par jour (CSS, thème-aware).
function FootfallChart({ series }) {
  const max = Math.max(1, ...series.map((s) => Math.max(s.entries, s.exits)));
  return (
    <div>
      <div className="flex items-end gap-2 h-40">
        {series.map((s) => (
          <div key={s.date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
            <div className="flex items-end gap-1 h-32 w-full justify-center">
              <div className="w-3 rounded-t bg-emerald-500/90" style={{ height: `${Math.max(2, (s.entries / max) * 100)}%` }}
                title={`${s.entries} entrées`} />
              <div className="w-3 rounded-t bg-amber-500/90" style={{ height: `${Math.max(2, (s.exits / max) * 100)}%` }}
                title={`${s.exits} sorties`} />
            </div>
            <span className="text-[10px] text-gray-500 dark:text-gray-400 truncate w-full text-center">{s.date.slice(5)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-3 text-xs text-gray-600 dark:text-gray-400">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" /> Entrées</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-amber-500" /> Sorties</span>
      </div>
    </div>
  );
}

function Kpi({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="text-2xl font-semibold text-gray-900 dark:text-white mt-1">{value}</p>
      {hint && <p className="text-[11px] text-gray-400 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function AnalyticsPage() {
  const user = useAuth();
  const role = user?.role || "viewer";
  const [isCollapsed, setIsCollapsed] = useState(false);

  const [summary, setSummary] = useState(null);
  const [footfall, setFootfall] = useState(null);
  const [queues, setQueues] = useState([]);
  const [occZones, setOccZones] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, f, q, o] = await Promise.all([
        fetchWithRefresh("/api/analytics/summary"),
        fetchWithRefresh("/api/analytics/footfall?days=7"),
        fetchWithRefresh("/api/analytics/queues"),
        fetchWithRefresh("/api/analytics/occupancy?hours=24"),
      ]);
      setSummary(s?.ok ? await s.json() : null);
      setFootfall(f?.ok ? await f.json() : null);
      setQueues(q?.ok ? (await q.json()).queues || [] : []);
      setOccZones(o?.ok ? (await o.json()).zones || [] : []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (user && !["admin", "user", "viewer"].includes(role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/analytics" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={role} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/analytics" />
        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar title="Analytics" subtitle="Fréquentation, occupation et files d'attente" showSearch={false} />

          <div className="p-6 space-y-6">
            {/* KPIs du jour */}
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
              <Kpi label="Entrées (jour)" value={loading ? "—" : (summary?.entries_today ?? 0)} />
              <Kpi label="Sorties (jour)" value={loading ? "—" : (summary?.exits_today ?? 0)} />
              <Kpi label="Présents (est.)" value={loading ? "—" : (summary?.present_now_estimate ?? 0)} hint="entrées − sorties" />
              <Kpi label="Occupation" value={loading ? "—" : (summary?.current_occupancy ?? 0)} hint="somme des zones" />
              <Kpi label="Attroupements" value={loading ? "—" : (summary?.crowd_alerts_today ?? 0)} hint="aujourd'hui" />
              <Kpi label="Attente moy." value={loading ? "—" : fmtWait(summary?.avg_wait_s)} hint="files" />
            </div>

            {/* Fréquentation 7 jours */}
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Fréquentation (7 jours)</h3>
                {footfall && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {footfall.total_entries} entrées · {footfall.total_exits} sorties
                  </span>
                )}
              </div>
              {loading ? (
                <div className="h-40 rounded-xl bg-black/5 dark:bg-white/5 animate-pulse" />
              ) : footfall?.series?.length ? (
                <FootfallChart series={footfall.series} />
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400 py-10 text-center">Aucune donnée de comptage (dessinez une ligne de comptage dans « Zones »).</p>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Files d'attente */}
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Files d&apos;attente</h3>
                {queues.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">Aucune zone de type « file ». Créez-en une dans « Zones ».</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 dark:text-gray-400 uppercase">
                        <th className="py-2">File</th><th className="py-2">Longueur</th><th className="py-2">Attente moy.</th><th className="py-2">Attente max</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {queues.map((q) => (
                        <tr key={q.zone_id}>
                          <td className="py-2 text-gray-900 dark:text-white">{q.name}</td>
                          <td className="py-2 font-semibold">{q.length}</td>
                          <td className="py-2">{fmtWait(q.wait_avg_s)}</td>
                          <td className="py-2">{fmtWait(q.wait_max_s)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Occupation par zone */}
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Occupation par zone</h3>
                {occZones.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">Aucune occupation récente. Dessinez des zones et activez une caméra.</p>
                ) : (
                  <ul className="space-y-2">
                    {occZones.map((z) => (
                      <li key={z.zone_id} className="flex items-center justify-between">
                        <span className="text-sm text-gray-900 dark:text-white truncate">{z.zone_name || `Zone ${z.zone_id}`}</span>
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">{z.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "./AdminSidebar";
import AdminTopBar from "./AdminTopBar";
import { useAuth } from "./AuthContext";
import { fetchWithRefresh } from "../../lib/fetchWithRefresh";

const ALERT_LEVEL = {
  blacklist_detected: { label: "Critique", cls: "bg-red-500/15 text-red-600 dark:text-red-300" },
  intrusion: { label: "Élevé", cls: "bg-orange-500/15 text-orange-600 dark:text-orange-300" },
  unauthorized_access: { label: "Moyen", cls: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-300" },
  suspicious_activity: { label: "Moyen", cls: "bg-purple-500/15 text-purple-600 dark:text-purple-300" },
  motion_detected: { label: "Faible", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-300" },
  crowd_detected: { label: "Faible", cls: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300" },
  loitering: { label: "Faible", cls: "bg-gray-500/15 text-gray-600 dark:text-gray-300" },
};

const EVENT_LABELS = {
  blacklist_detected: "Blacklist détectée",
  intrusion: "Intrusion",
  unauthorized_access: "Accès non autorisé",
  suspicious_activity: "Activité suspecte",
  motion_detected: "Mouvement détecté",
  crowd_detected: "Foule détectée",
  loitering: "Rôdage",
};

function formatRelative(dateString) {
  if (!dateString) return "—";
  const diff = Date.now() - new Date(dateString).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  if (minutes < 1) return "À l'instant";
  if (minutes < 60) return `Il y a ${minutes} min`;
  if (hours < 24) return `Il y a ${hours}h`;
  return new Date(dateString).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

// Mini graphe à barres (SVG/flex, sans dépendance) — activité par jour.
function MiniBarChart({ data }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="flex items-end gap-1.5 h-32">
      {data.map((d) => (
        <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group">
          <div className="w-full flex items-end justify-center h-full">
            <div
              className="w-full max-w-[28px] rounded-t-md bg-indigo-500/80 group-hover:bg-indigo-500 transition-all"
              style={{ height: `${Math.max(4, (d.count / max) * 100)}%` }}
              title={`${d.count} événement(s)`}
            />
          </div>
          <span className="text-[10px] text-black/50 dark:text-white/50">
            {new Date(d.date).toLocaleDateString("fr-FR", { weekday: "short" })}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function AdminDashboard() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const [cameras, setCameras] = useState([]);
  const [users, setUsers] = useState([]);
  const [people, setPeople] = useState([]);
  const [events, setEvents] = useState([]);
  const [dash, setDash] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [lastSync, setLastSync] = useState(null);

  const fetchDashboardData = useCallback(async () => {
    setLoadingStats(true);
    try {
      const [camRes, userRes, peopleRes, eventsRes, dashRes] = await Promise.all([
        fetchWithRefresh("/api/cameras"),
        fetchWithRefresh("/api/users"),
        fetchWithRefresh("/api/people"),
        fetchWithRefresh("/api/events?limit=20"),
        fetchWithRefresh("/api/dashboard"),
      ]);

      if (camRes?.ok) setCameras(await camRes.json());
      if (userRes?.ok) setUsers(await userRes.json());
      if (peopleRes?.ok) setPeople(await peopleRes.json());
      if (eventsRes?.ok) setEvents(await eventsRes.json());
      if (dashRes?.ok) setDash(await dashRes.json());

      setLastSync(new Date());
    } finally {
      setLoadingStats(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const activeCameras = cameras.filter((c) => c.is_active);
  const offlineCameras = cameras.filter((c) => !c.is_active);
  const todayEvents = events.filter((e) => {
    if (!e.timestamp) return false;
    const d = new Date(e.timestamp);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  });
  const statCards = [
    {
      label: "Caméras actives",
      value: loadingStats ? "—" : activeCameras.length,
      delta: loadingStats ? "" : `${cameras.length} total`,
      trend: "live",
      deltaGood: true,
    },
    {
      label: "Alertes aujourd'hui",
      value: loadingStats ? "—" : todayEvents.length,
      delta: loadingStats ? "" : `${dash?.counts.alerts_new ?? 0} alertes blacklist`,
      trend: "24h",
      deltaGood: (dash?.counts.alerts_new ?? 0) === 0,
    },
    {
      label: "Sous surveillance",
      value: loadingStats ? "—" : (dash?.counts.people_blacklisted ?? 0),
      delta: loadingStats ? "" : `${dash?.counts.people_blacklisted ?? 0} personne(s) surveillée(s)`,
      trend: "blacklist",
      deltaGood: true,
    },
    {
      label: "Utilisateurs",
      value: loadingStats ? "—" : users.length,
      delta: loadingStats ? "" : `${users.filter((u) => u.is_active).length} actifs`,
      trend: "total",
      deltaGood: true,
    },
  ];

  const recentAlerts = events.slice(0, 3);

  const syncLabel = lastSync
    ? `Dernière sync : il y a ${Math.max(0, Math.floor((Date.now() - lastSync.getTime()) / 60000))} min`
    : "Chargement…";

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Tableau de bord"
            subtitle={syncLabel}
            searchPlaceholder="Rechercher une caméra, un utilisateur…"
            actions={
              <button
                onClick={fetchDashboardData}
                className="rounded-xl border border-black/10 dark:border-white/10 px-4 py-2.5 text-sm font-medium hover:bg-black/5 dark:hover:bg-white/5 transition-colors flex items-center gap-2"
              >
                <svg className={`h-4 w-4 ${loadingStats ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 4v6h-6M1 20v-6h6" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
                Actualiser
              </button>
            }
          />

          <div className="p-6 sm:p-10 space-y-8">
            {/* Cartes stats */}
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {statCards.map((card) => (
                <div
                  key={card.label}
                  className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-black/60 dark:text-white/60">{card.label}</p>
                    <span className="text-[10px] text-black/50 dark:text-white/50 uppercase">
                      {card.trend}
                    </span>
                  </div>
                  <div className="mt-3 flex items-end justify-between">
                    <p className="text-2xl font-semibold">{card.value}</p>
                    {card.delta && (
                      <span className={`text-xs rounded-full px-2 py-0.5 ${
                        card.deltaGood
                          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                          : "bg-red-500/15 text-red-600 dark:text-red-300"
                      }`}>
                        {card.delta}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 h-2 w-full rounded-full bg-black/10 dark:bg-white/10">
                    <div
                      className={`h-2 rounded-full ${card.deltaGood ? "bg-emerald-500" : "bg-red-500"}`}
                      style={{
                        width: loadingStats
                          ? "0%"
                          : card.label === "Caméras actives" && cameras.length > 0
                          ? `${Math.round((activeCameras.length / cameras.length) * 100)}%`
                          : card.label === "Alertes aujourd'hui" && todayEvents.length > 0
                          ? `${Math.min(100, (todayEvents.length / 50) * 100)}%`
                          : "40%",
                      }}
                    />
                  </div>
                </div>
              ))}
            </section>

            {/* Activité 7 jours + répartition par type (KPI réels) */}
            <section className="grid gap-6 xl:grid-cols-[1.4fr_0.6fr]">
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <h3 className="font-semibold">Activité (7 derniers jours)</h3>
                <p className="text-xs text-black/50 dark:text-white/50 mt-0.5">Événements détectés par jour</p>
                <div className="mt-5">
                  {dash
                    ? <MiniBarChart data={dash.events_by_day} />
                    : <div className="h-32 animate-pulse rounded-xl bg-black/5 dark:bg-white/5" />}
                </div>
              </div>
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <h3 className="font-semibold">Répartition par type</h3>
                <div className="mt-4 space-y-2.5">
                  {dash && Object.keys(dash.events_by_type).length > 0 ? (
                    Object.entries(dash.events_by_type)
                      .sort((a, b) => b[1] - a[1])
                      .map(([type, n]) => {
                        const total = Object.values(dash.events_by_type).reduce((s, v) => s + v, 0) || 1;
                        return (
                          <div key={type}>
                            <div className="flex items-center justify-between text-xs">
                              <span className="text-black/70 dark:text-white/70 truncate">{type}</span>
                              <span className="font-semibold ml-2">{n}</span>
                            </div>
                            <div className="mt-1 h-1.5 rounded-full bg-black/10 dark:bg-white/10">
                              <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${Math.round((n / total) * 100)}%` }} />
                            </div>
                          </div>
                        );
                      })
                  ) : (
                    <p className="text-xs text-black/50 dark:text-white/50">Aucun événement enregistré.</p>
                  )}
                </div>
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
              {/* Flux en direct */}
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Flux en direct prioritaires</h3>
                  <button className="text-xs text-black/60 dark:text-white/60 hover:underline">
                    Gérer les vues
                  </button>
                </div>
                <div className="mt-4 grid gap-5 sm:grid-cols-2">
                  {loadingStats
                    ? Array(4).fill(null).map((_, i) => (
                        <div key={i} className="h-44 sm:h-52 rounded-2xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 animate-pulse" />
                      ))
                    : (activeCameras.length > 0 ? activeCameras.slice(0, 4) : cameras.slice(0, 4)).map((cam, i) => (
                        <div
                          key={cam.id || i}
                          className="h-44 sm:h-52 rounded-2xl border border-black/10 dark:border-white/10 bg-gradient-to-br from-black/10 to-black/0 dark:from-white/10 dark:to-white/0 flex flex-col items-end justify-end p-4"
                        >
                          <div className="flex items-center gap-2 w-full justify-between">
                            <span className="text-xs text-black/70 dark:text-white/70 truncate">
                              {cam.cam_name || cam.location || `Caméra #${cam.id}`}
                            </span>
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                              cam.is_active
                                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                                : "bg-gray-500/15 text-gray-600 dark:text-gray-300"
                            }`}>
                              <span className={`h-1.5 w-1.5 rounded-full ${cam.is_active ? "bg-emerald-500 animate-pulse" : "bg-gray-400"}`} />
                              {cam.is_active ? "En ligne" : "Hors ligne"}
                            </span>
                          </div>
                          {cam.location && (
                            <p className="text-[11px] text-black/50 dark:text-white/50 w-full mt-1">{cam.location}</p>
                          )}
                        </div>
                      ))}
                  {!loadingStats && cameras.length === 0 && (
                    <div className="col-span-2 flex items-center justify-center h-44 text-sm text-black/40 dark:text-white/40">
                      Aucune caméra configurée
                    </div>
                  )}
                </div>
              </div>

              {/* Activité récente */}
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <h3 className="font-semibold">Activité récente</h3>
                <div className="mt-4 space-y-3 text-sm">
                  {loadingStats ? (
                    Array(4).fill(null).map((_, i) => (
                      <div key={i} className="h-12 rounded-xl bg-black/5 dark:bg-white/5 animate-pulse" />
                    ))
                  ) : events.length === 0 ? (
                    <p className="text-sm text-black/40 dark:text-white/40 text-center py-4">
                      Aucun événement récent
                    </p>
                  ) : (
                    events.slice(0, 5).map((evt) => (
                      <div
                        key={evt.id}
                        className="flex items-start gap-3 rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 p-3"
                      >
                        <span className={`mt-1 h-2 w-2 rounded-full flex-shrink-0 ${
                          ["blacklist_detected", "intrusion"].includes(evt.event_type)
                            ? "bg-red-500"
                            : "bg-emerald-500"
                        }`} />
                        <div className="min-w-0">
                          <p className="text-sm text-black/80 dark:text-white/80 truncate">
                            {EVENT_LABELS[evt.event_type] || evt.event_type} — {evt.camera_nom}
                          </p>
                          <p className="text-[11px] text-black/50 dark:text-white/50 mt-0.5">
                            {formatRelative(evt.timestamp)}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {/* Caméras hors ligne */}
                <div className="mt-6 rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 p-4">
                  <p className="text-xs text-black/60 dark:text-white/60">Caméras hors ligne</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {loadingStats ? "—" : offlineCameras.length}
                  </p>
                  {!loadingStats && offlineCameras.length > 0 && (
                    <p className="mt-1 text-xs text-black/50 dark:text-white/50">
                      {offlineCameras.slice(0, 2).map((c) => c.cam_name || `#${c.id}`).join(", ")}
                      {offlineCameras.length > 2 && ` +${offlineCameras.length - 2}`}
                    </p>
                  )}
                </div>
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
              {/* Alertes critiques */}
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Alertes critiques</h3>
                  <a href="/Osirion/admin/alerts" className="text-xs text-black/60 dark:text-white/60 hover:underline">
                    Voir toutes
                  </a>
                </div>
                <div className="mt-4 space-y-4">
                  {loadingStats ? (
                    Array(3).fill(null).map((_, i) => (
                      <div key={i} className="h-16 rounded-xl bg-black/5 dark:bg-white/5 animate-pulse" />
                    ))
                  ) : recentAlerts.length === 0 ? (
                    <p className="text-sm text-black/40 dark:text-white/40 text-center py-6">
                      Aucune alerte récente
                    </p>
                  ) : (
                    recentAlerts.map((alert) => {
                      const level = ALERT_LEVEL[alert.event_type] || { label: "Info", cls: "bg-gray-500/15 text-gray-600 dark:text-gray-300" };
                      return (
                        <div
                          key={alert.id}
                          className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 p-4"
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium truncate">
                              {EVENT_LABELS[alert.event_type] || alert.event_type}
                            </p>
                            <span className={`text-[10px] uppercase tracking-wide rounded-full px-2 py-0.5 ${level.cls}`}>
                              {level.label}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-black/60 dark:text-white/60">
                            {alert.camera_nom} — {alert.camera_location}
                          </p>
                          <p className="mt-2 text-[11px] text-black/50 dark:text-white/50">
                            {formatRelative(alert.timestamp)}
                          </p>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Récap reconnaissance faciale */}
              <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-black/40 p-6">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">Reconnaissances faciales</h3>
                  <a href="/Osirion/admin/alerts" className="text-xs text-black/60 dark:text-white/60 hover:underline">
                    Voir le journal
                  </a>
                </div>
                <div className="mt-4 space-y-3">
                  {loadingStats ? (
                    Array(3).fill(null).map((_, i) => (
                      <div key={i} className="h-14 rounded-xl bg-black/5 dark:bg-white/5 animate-pulse" />
                    ))
                  ) : events.filter((e) => e.event_type === "blacklist_detected").length === 0 ? (
                    <p className="text-sm text-black/40 dark:text-white/40 text-center py-6">
                      Aucune correspondance récente
                    </p>
                  ) : (
                    events
                      .filter((e) => e.event_type === "blacklist_detected")
                      .slice(0, 3)
                      .map((item) => {
                        const confidencePct = item.confidence ? Math.round(item.confidence * 100) : null;
                        return (
                          <div
                            key={item.id}
                            className="flex items-center justify-between rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 px-4 py-3"
                          >
                            <div className="min-w-0">
                              <p className="text-sm font-medium truncate">
                                {item.person_nom || `Caméra ${item.camera_nom}`}
                              </p>
                              <p className="text-xs text-black/60 dark:text-white/60 mt-0.5">
                                {formatRelative(item.timestamp)}
                              </p>
                            </div>
                            {confidencePct !== null && (
                              <span className="text-xs rounded-full bg-black/10 dark:bg-white/15 px-2 py-0.5 ml-3 flex-shrink-0">
                                {confidencePct}%
                              </span>
                            )}
                          </div>
                        );
                      })
                  )}
                </div>

                {/* Résumé blacklist */}
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 p-3 text-center">
                    <p className="text-xs text-black/60 dark:text-white/60">Blacklist</p>
                    <p className="text-xl font-semibold mt-1">{loadingStats ? "—" : people.length}</p>
                  </div>
                  <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-black/30 p-3 text-center">
                    <p className="text-xs text-black/60 dark:text-white/60">Détections</p>
                    <p className="text-xl font-semibold mt-1">
                      {loadingStats ? "—" : events.filter((e) => e.event_type === "blacklist_detected").length}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

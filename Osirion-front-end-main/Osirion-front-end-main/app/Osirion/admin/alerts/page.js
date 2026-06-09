"use client";

import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

// ── Icônes SVG inline (auto-contenues) ──────────────────────────────────────
const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IconUser = ({ className }) => (<Svg className={className}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>);
const IconCar = ({ className }) => (<Svg className={className}><path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" /><rect x="3" y="11" width="18" height="6" rx="2" /><circle cx="7.5" cy="17.5" r="1.5" /><circle cx="16.5" cy="17.5" r="1.5" /></Svg>);
const IconCheck = ({ className }) => (<Svg className={className}><path d="M20 6 9 17l-5-5" /></Svg>);
const IconBell = ({ className }) => (<Svg className={className}><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></Svg>);
const IconRefresh = ({ className }) => (<Svg className={className}><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" /></Svg>);
const IconInbox = ({ className }) => (<Svg className={className}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5 5h14l3 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6z" /></Svg>);
const IconArchive = ({ className }) => (<Svg className={className}><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M9 12h6" /></Svg>);

const STATUS_META = {
  new:          { label: "Nouvelle",  badge: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300" },
  acknowledged: { label: "Acquittée", badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" },
  resolved:     { label: "Résolue",   badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" },
};

const FILTERS = [
  { id: "tous", label: "Toutes" },
  { id: "new", label: "Nouvelles" },
  { id: "acknowledged", label: "Acquittées" },
  { id: "resolved", label: "Résolues" },
];

function relTime(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "—";
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  if (diffMin < 1440) return `il y a ${Math.floor(diffMin / 60)} h`;
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function AlertsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [statusFilter, setStatusFilter] = useState("tous");
  const [busyId, setBusyId] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);   // { ok, text }

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const notifyAvailable = !!(stats?.notifications?.email || stats?.notifications?.webhook);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const qs = statusFilter !== "tous" ? `?status=${statusFilter}` : "";
      const res = await fetchWithRefresh(`/api/alerts${qs}`);
      if (!res) return;
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFetchError(d?.message || "Erreur de chargement.");
        return;
      }
      setAlerts(await res.json());
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetchWithRefresh("/api/alerts/stats");
      if (res && res.ok) setStats(await res.json());
    } catch { /* non bloquant */ }
  }, []);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);
  useEffect(() => { loadStats(); }, [loadStats]);

  const flash = (ok, text) => {
    setActionMsg({ ok, text });
    setTimeout(() => setActionMsg(null), 4000);
  };

  const doAction = async (alert, action, body) => {
    setBusyId(alert.id);
    try {
      const res = await fetchWithRefresh(`/api/alerts/${alert.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = res ? await res.json().catch(() => ({})) : {};
      if (!res || !res.ok) {
        flash(false, data?.message || "Échec de l'action.");
        return;
      }
      if (action === "notify") {
        flash(true, `Notification envoyée (${data.notified_channel || "ok"}).`);
      }
      await Promise.all([loadAlerts(), loadStats()]);
    } catch {
      flash(false, "Erreur réseau.");
    } finally {
      setBusyId(null);
    }
  };

  if (user && !["admin", "user"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/alerts" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  const statCount = (k) => (stats ? stats[k] ?? 0 : "—");

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/alerts"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Alertes"
            subtitle="Détections de personnes / plaques sous surveillance"
            showSearch={false}
            actions={
              <button
                onClick={() => { loadAlerts(); loadStats(); }}
                className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <IconRefresh className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Actualiser
              </button>
            }
          />

          <div className="p-6 space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { k: "total", label: "Total" },
                { k: "new", label: "Nouvelles" },
                { k: "acknowledged", label: "Acquittées" },
                { k: "resolved", label: "Résolues" },
              ].map((s) => (
                <div key={s.k} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400">{s.label}</div>
                  <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">{statCount(s.k)}</div>
                </div>
              ))}
            </div>

            {/* Avertissement notifications non configurées */}
            {stats && !notifyAvailable && (
              <div className="rounded-xl border border-amber-300/60 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                ⓘ Aucun canal de notification configuré (SMTP / webhook). Le bouton « Notifier » restera indisponible tant que <code className="font-mono">SMTP_HOST</code> ou <code className="font-mono">ALERT_WEBHOOK_URL</code> ne sont pas renseignés côté backend.
              </div>
            )}

            {/* Message d'action */}
            {actionMsg && (
              <div className={`rounded-xl px-4 py-3 text-sm font-medium ${actionMsg.ok ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" : "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300"}`}>
                {actionMsg.text}
              </div>
            )}

            {/* Filtres */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-2">
              <div className="flex gap-2 overflow-x-auto">
                {FILTERS.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setStatusFilter(f.id)}
                    className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all ${
                      statusFilter === f.id
                        ? "bg-gray-900 dark:bg-white text-white dark:text-gray-900"
                        : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Liste */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
              {fetchError ? (
                <div className="p-10 text-center">
                  <p className="text-sm text-rose-600 dark:text-rose-400">{fetchError}</p>
                  <button onClick={loadAlerts} className="mt-3 text-sm font-medium text-indigo-600 hover:underline">Réessayer</button>
                </div>
              ) : loading ? (
                <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
                  <IconRefresh className="h-6 w-6 mx-auto mb-3 animate-spin opacity-60" /> Chargement…
                </div>
              ) : alerts.length === 0 ? (
                <div className="p-12 text-center">
                  <IconInbox className="h-10 w-10 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">Aucune alerte {statusFilter !== "tous" ? "dans ce statut" : "pour le moment"}.</p>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {alerts.map((a) => {
                    const meta = STATUS_META[a.status] || STATUS_META.new;
                    const src = a.snapshot_url
                      ? (String(a.snapshot_url).startsWith("http") ? a.snapshot_url : `/api/images?path=${encodeURIComponent(a.snapshot_url)}`)
                      : null;
                    const busy = busyId === a.id;
                    return (
                      <li key={a.id} className="flex items-center gap-4 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors">
                        {/* Vignette */}
                        <div className="shrink-0 h-14 w-14 rounded-xl bg-gray-100 dark:bg-gray-800 overflow-hidden flex items-center justify-center text-gray-400">
                          {src ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={src} alt="snapshot" className="h-full w-full object-cover" />
                          ) : a.kind === "plate" ? <IconCar className="h-6 w-6" /> : <IconUser className="h-6 w-6" />}
                        </div>

                        {/* Infos */}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-bold text-gray-900 dark:text-white truncate">{a.label}</span>
                            <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${meta.badge}`}>{meta.label}</span>
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                              {a.kind === "plate" ? "Plaque" : "Personne"}
                            </span>
                            {a.notified_at && (
                              <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                                Notifié ({a.notified_channel})
                              </span>
                            )}
                          </div>
                          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">
                            {a.reason ? `${a.reason} · ` : ""}{a.camera_name || `Caméra ${a.camera_id ?? "?"}`} · {relTime(a.created_at)}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="shrink-0 flex items-center gap-2">
                          {a.status !== "resolved" && (
                            <button
                              onClick={() => doAction(a, "notify", { channel: "both" })}
                              disabled={busy || !notifyAvailable}
                              title={notifyAvailable ? "Envoyer une notification (email/webhook)" : "Notifications non configurées"}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              <IconBell className="h-3.5 w-3.5" /> Notifier
                            </button>
                          )}
                          {a.status === "new" && (
                            <button
                              onClick={() => doAction(a, "acknowledge")}
                              disabled={busy}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                              <IconCheck className="h-3.5 w-3.5" /> Acquitter
                            </button>
                          )}
                          {a.status !== "resolved" && (
                            <button
                              onClick={() => doAction(a, "resolve")}
                              disabled={busy}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                              <IconArchive className="h-3.5 w-3.5" /> Résoudre
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

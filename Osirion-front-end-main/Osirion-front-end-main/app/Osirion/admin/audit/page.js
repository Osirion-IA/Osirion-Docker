"use client";

import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IconRefresh = ({ className }) => (<Svg className={className}><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" /></Svg>);
const IconTrash = ({ className }) => (<Svg className={className}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" /></Svg>);
const IconShield = ({ className }) => (<Svg className={className}><path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" /></Svg>);

// Couleur de badge par famille d'action.
function actionBadge(action) {
  if (action.startsWith("login.failure") || action.startsWith("login.locked"))
    return "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300";
  if (action.startsWith("login")) return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300";
  if (action.startsWith("user")) return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
  if (action.startsWith("maintenance")) return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
  if (action.startsWith("password")) return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300";
  return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
}

export default function AuditPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  // Maintenance / purge
  const [days, setDays] = useState(90);
  const [preview, setPreview] = useState(null);   // { to_delete, total_events }
  const [purging, setPurging] = useState(false);
  const [maintMsg, setMaintMsg] = useState(null); // { ok, text }

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const res = await fetchWithRefresh("/api/audit");
      if (!res) return;
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFetchError(d?.message || "Erreur de chargement.");
        return;
      }
      setLogs(await res.json());
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  const doPreview = async () => {
    setMaintMsg(null);
    setPreview(null);
    try {
      const res = await fetchWithRefresh(`/api/maintenance/purge-preview?days=${days}`);
      if (res && res.ok) setPreview(await res.json());
      else setMaintMsg({ ok: false, text: "Aperçu impossible." });
    } catch {
      setMaintMsg({ ok: false, text: "Erreur réseau." });
    }
  };

  const doPurge = async () => {
    setPurging(true);
    setMaintMsg(null);
    try {
      const res = await fetchWithRefresh(`/api/maintenance/purge?days=${days}`, { method: "POST" });
      const data = res ? await res.json().catch(() => ({})) : {};
      if (res && res.ok) {
        setMaintMsg({ ok: true, text: `${data.deleted_events} événement(s) et ${data.removed_snapshots} snapshot(s) supprimés.` });
        setPreview(null);
        loadLogs();
      } else {
        setMaintMsg({ ok: false, text: data?.message || "Échec de la purge." });
      }
    } catch {
      setMaintMsg({ ok: false, text: "Erreur réseau." });
    } finally {
      setPurging(false);
    }
  };

  if (user && user.role !== "admin") {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/audit" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/audit"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Audit & Maintenance"
            subtitle="Journal des actions sensibles et rétention des données"
            showSearch={false}
            actions={
              <button
                onClick={loadLogs}
                className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <IconRefresh className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Actualiser
              </button>
            }
          />

          <div className="p-6 space-y-6">
            {/* Maintenance / purge */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-10 w-10 rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-300 flex items-center justify-center">
                  <IconTrash className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-gray-900 dark:text-white">Rétention des données</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Purge manuelle des événements et snapshots anciens (action irréversible)</p>
                </div>
              </div>

              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Supprimer les événements de plus de (jours)</label>
                  <input
                    type="number"
                    min="1"
                    max="3650"
                    value={days}
                    onChange={(e) => { setDays(parseInt(e.target.value) || 1); setPreview(null); }}
                    className="w-40 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
                <button
                  onClick={doPreview}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 px-4 py-2 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  Aperçu
                </button>
                {preview && (
                  <button
                    onClick={doPurge}
                    disabled={purging || preview.to_delete === 0}
                    className="rounded-lg bg-rose-600 text-white px-4 py-2 text-sm font-semibold hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    <IconTrash className="h-4 w-4" />
                    Purger {preview.to_delete} événement(s)
                  </button>
                )}
              </div>

              {preview && (
                <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
                  <b>{preview.to_delete}</b> événement(s) seraient supprimés sur <b>{preview.total_events}</b> au total.
                  {preview.to_delete > 0 && " Cette action est irréversible."}
                </p>
              )}
              {maintMsg && (
                <p className={`mt-3 text-sm font-medium ${maintMsg.ok ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                  {maintMsg.text}
                </p>
              )}
            </div>

            {/* Journal d'audit */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100 dark:border-gray-800">
                <IconShield className="h-4 w-4 text-gray-500" />
                <h3 className="text-sm font-bold text-gray-900 dark:text-white">Journal d&apos;audit</h3>
              </div>

              {fetchError ? (
                <div className="p-10 text-center">
                  <p className="text-sm text-rose-600 dark:text-rose-400">{fetchError}</p>
                </div>
              ) : loading ? (
                <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
                  <IconRefresh className="h-6 w-6 mx-auto mb-3 animate-spin opacity-60" /> Chargement…
                </div>
              ) : logs.length === 0 ? (
                <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">Aucune entrée d&apos;audit.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 dark:bg-gray-800/50 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                        <th className="px-4 py-3">Date</th>
                        <th className="px-4 py-3">Action</th>
                        <th className="px-4 py-3">Utilisateur</th>
                        <th className="px-4 py-3">Cible</th>
                        <th className="px-4 py-3">Détail</th>
                        <th className="px-4 py-3">IP</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {logs.map((l) => (
                        <tr key={l.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                          <td className="px-4 py-3 whitespace-nowrap text-gray-500 dark:text-gray-400">
                            {new Date(l.created_at).toLocaleString("fr-FR")}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${actionBadge(l.action)}`}>{l.action}</span>
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-gray-700 dark:text-gray-300">{l.user_email || "—"}</td>
                          <td className="px-4 py-3 whitespace-nowrap text-gray-500 dark:text-gray-400">
                            {l.target_type ? `${l.target_type}#${l.target_id ?? "?"}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-gray-500 dark:text-gray-400 max-w-[280px] truncate">{l.detail || "—"}</td>
                          <td className="px-4 py-3 whitespace-nowrap font-mono text-xs text-gray-400">{l.ip_address || "—"}</td>
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

"use client";

/**
 * Audit & maintenance — section Configurer (thème clair). Journal des actions
 * sensibles + rétention (purge des événements/snapshots anciens). Admin only.
 */
import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Trash2, ShieldCheck } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, RefreshButton, EmptyState, SkeletonRows } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

function actionColor(a = "") {
  if (a.startsWith("login.fail") || a.startsWith("login.locked")) return "var(--os-red)";
  if (a.startsWith("login")) return "var(--os-green)";
  if (a.startsWith("user")) return "var(--os-blue)";
  if (a.startsWith("maintenance")) return "var(--os-amber)";
  return "var(--os-t3)";
}

export default function AuditPage() {
  const user = useAuth();
  const isAdmin = user?.role === "admin";
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(90);
  const [preview, setPreview] = useState(null);
  const [purging, setPurging] = useState(false);
  const [msg, setMsg] = useState(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithRefresh("/api/audit");
      const d = res && res.ok ? await res.json() : [];
      setLogs(Array.isArray(d) ? d : (d?.logs || []));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { if (isAdmin) loadLogs(); }, [loadLogs, isAdmin]);

  const doPreview = async () => {
    setMsg(null); setPreview(null);
    const res = await fetchWithRefresh(`/api/maintenance/purge-preview?days=${days}`);
    if (res && res.ok) setPreview(await res.json()); else setMsg({ ok: false, text: "Aperçu impossible." });
  };
  const doPurge = async () => {
    setPurging(true); setMsg(null);
    try {
      const res = await fetchWithRefresh(`/api/maintenance/purge?days=${days}`, { method: "POST" });
      const data = res ? await res.json().catch(() => ({})) : {};
      if (res && res.ok) { setMsg({ ok: true, text: `${data.deleted_events} événement(s) et ${data.removed_snapshots} snapshot(s) supprimés.` }); setPreview(null); loadLogs(); }
      else setMsg({ ok: false, text: data?.message || "Échec de la purge." });
    } finally { setPurging(false); }
  };

  if (user && !isAdmin) {
    return <OsShell><div className="p-6"><Card className="p-10 text-center"><p className="text-[14px] text-os-t2">Accès réservé aux administrateurs.</p></Card></div></OsShell>;
  }

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader title="Audit & maintenance" subtitle="Journal des actions sensibles et rétention des données" actions={<RefreshButton onClick={loadLogs} spinning={loading} />} />

        <Card className="p-5 mb-5">
          <div className="flex items-center gap-3 mb-4">
            <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-amber"><Trash2 className="h-5 w-5" /></span>
            <div><h3 className="text-[15px] font-semibold text-os-t1">Rétention des données</h3><p className="text-[12px] text-os-t3">Purge des événements et snapshots anciens (action irréversible)</p></div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[12px] text-os-t3 mb-1.5">Supprimer les événements de plus de (jours)</label>
              <input type="number" min="1" max="3650" value={days} onChange={(e) => { setDays(parseInt(e.target.value) || 1); setPreview(null); }}
                className="w-40 rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 os-num outline-none focus:border-os-t3" />
            </div>
            <button onClick={doPreview} className="px-4 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1">Aperçu</button>
            {preview && (
              <button onClick={doPurge} disabled={purging || preview.to_delete === 0}
                className="px-4 py-2 rounded-os text-[13px] font-semibold text-white inline-flex items-center gap-2 disabled:opacity-40" style={{ background: "var(--os-red)" }}>
                <Trash2 className="h-4 w-4" /> Purger {preview.to_delete}
              </button>
            )}
          </div>
          {preview && <p className="mt-3 text-[13px] text-os-t2"><b className="os-num">{preview.to_delete}</b> événement(s) sur <b className="os-num">{preview.total_events}</b> — {preview.to_delete > 0 ? "action irréversible." : "rien à supprimer."}</p>}
          {msg && <p className="mt-3 text-[13px] font-medium" style={{ color: msg.ok ? "var(--os-green)" : "var(--os-red)" }}>{msg.text}</p>}
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-4 border-b border-os-border">
            <ShieldCheck className="h-4 w-4 text-os-t3" />
            <h3 className="text-[14px] font-semibold text-os-t1">Journal d&apos;audit</h3>
          </div>
          {loading ? <div className="p-5"><SkeletonRows count={8} /></div>
            : logs.length === 0 ? <EmptyState icon={ShieldCheck}>Aucune entrée d&apos;audit.</EmptyState>
            : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px] min-w-[640px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-os-t3 border-b border-os-border">
                      <th className="px-4 py-3 font-semibold">Date</th><th className="px-4 py-3 font-semibold">Action</th><th className="px-4 py-3 font-semibold">Utilisateur</th><th className="px-4 py-3 font-semibold">Cible</th><th className="px-4 py-3 font-semibold">Détail</th><th className="px-4 py-3 font-semibold">IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((l) => (
                      <tr key={l.id} className="border-b border-os-border last:border-0">
                        <td className="px-4 py-3 os-num text-os-t3 whitespace-nowrap">{new Date(l.created_at).toLocaleString("fr-FR")}</td>
                        <td className="px-4 py-3 whitespace-nowrap"><span className="inline-flex items-center gap-1.5 font-medium text-os-t1"><span className="h-2 w-2 rounded-full" style={{ background: actionColor(l.action) }} />{l.action}</span></td>
                        <td className="px-4 py-3 text-os-t2 whitespace-nowrap">{l.user_email || "—"}</td>
                        <td className="px-4 py-3 text-os-t3 whitespace-nowrap os-num">{l.target_type ? `${l.target_type}#${l.target_id ?? "?"}` : "—"}</td>
                        <td className="px-4 py-3 text-os-t3 max-w-[280px] truncate">{l.detail || "—"}</td>
                        <td className="px-4 py-3 os-num text-[12px] text-os-t4 whitespace-nowrap">{l.ip_address || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </Card>
      </div>
    </OsShell>
  );
}

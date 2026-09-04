"use client";

/**
 * Centre d'alertes — section Surveiller (thème sombre). Liste + filtres par statut
 * + panneau détail avec workflow Déclenchée → Acquittée → Résolue. 100 % anonyme
 * (snapshot = boîtes anonymes). Données /api/alerts (+ stats, actions).
 */
import { useState, useEffect, useCallback } from "react";
import { Bell, Check, Archive, Send, Inbox, ChevronLeft, ChevronRight, CheckCheck } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { useAuth } from "../AuthContext";

const STATUS_META = {
  new: { label: "Nouvelle", color: "var(--os-red)" },
  acknowledged: { label: "Acquittée", color: "var(--os-amber)" },
  resolved: { label: "Résolue", color: "var(--os-green)" },
};
const KIND_LABEL = { queue: "File", crowd: "Attroupement", intrusion: "Intrusion", absence: "Poste vacant", staffing: "Sous-effectif", custom: "Alerte" };
const SEV_COLOR = { info: "var(--os-blue)", warning: "var(--os-amber)", critical: "var(--os-red)" };
const PAGE_SIZE = 12;

function relTime(ts) {
  const d = new Date(ts && !String(ts).endsWith("Z") ? `${ts}Z` : ts);
  if (isNaN(d)) return "—";
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  if (m < 1440) return `il y a ${Math.floor(m / 60)} h`;
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
const clock = (ts) => { const d = new Date(ts && !String(ts).endsWith("Z") ? `${ts}Z` : ts); return isNaN(d) ? "—" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); };
const snap = (u) => (u ? (String(u).startsWith("http") ? u : `/api/images?path=${encodeURIComponent(u)}`) : null);
function deliveryMeta(alert) {
  if (alert.notified_at) return { label: `Envoyée · ${alert.notified_channel || "canal inconnu"}`, color: "var(--os-green)" };
  if (alert.notify_next_retry_at) return { label: `Reprise prévue · essai ${Number(alert.notify_attempts || 0) + 1}`, color: "var(--os-amber)" };
  if (Number(alert.notify_attempts || 0) >= 5) return { label: "Non délivrée · tentatives épuisées", color: "var(--os-red)" };
  if (alert.notify_requested_channels) return { label: "En attente d’envoi", color: "var(--os-amber)" };
  return { label: "Aucune notification demandée", color: "var(--os-t4)" };
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("tous");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [busyBulk, setBusyBulk] = useState(false);
  const notifyAvailable = !!(stats?.notifications?.email || stats?.notifications?.webhook);
  const user = useAuth();
  const canResolve = ["admin", "user"].includes(user?.role || "viewer");

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "tous") params.set("status", statusFilter);
      params.set("skip", String(page * PAGE_SIZE));
      params.set("limit", String(PAGE_SIZE));
      const res = await fetchWithRefresh(`/api/alerts?${params.toString()}`);
      const data = res && res.ok ? await res.json() : [];
      setAlerts(Array.isArray(data) ? data : []);
    } finally { setLoading(false); }
  }, [statusFilter, page]);
  const loadStats = useCallback(async () => {
    const res = await fetchWithRefresh("/api/alerts/stats");
    if (res && res.ok) setStats(await res.json());
  }, []);
  useEffect(() => { loadAlerts(); }, [loadAlerts]);
  useEffect(() => { loadStats(); }, [loadStats]);

  const doAction = async (alert, action, body) => {
    setBusyId(alert.id);
    try {
      const res = await fetchWithRefresh(`/api/alerts/${alert.id}/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
      });
      if (res && res.ok) await Promise.all([loadAlerts(), loadStats()]);
    } finally { setBusyId(null); }
  };

  // Résolution GROUPÉE : selon le filtre courant, on résout les nouvelles, les
  // acquittées, ou toutes les non-résolues (« Toutes »). Le décompte cible vient
  // des stats globales (pas de la page affichée) → un seul appel suffit.
  const bulkStatus = statusFilter === "new" ? "new" : statusFilter === "acknowledged" ? "acknowledged" : null;
  const nNew = stats?.new ?? 0, nAck = stats?.acknowledged ?? 0;
  const bulkTarget = bulkStatus === "new" ? nNew : bulkStatus === "acknowledged" ? nAck : nNew + nAck;

  const resolveAll = async () => {
    if (!bulkTarget) return;
    if (!window.confirm(`Marquer ${bulkTarget} alerte${bulkTarget > 1 ? "s" : ""} comme résolue${bulkTarget > 1 ? "s" : ""} ?`)) return;
    setBusyBulk(true);
    try {
      const res = await fetchWithRefresh("/api/alerts/resolve-all", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: bulkStatus }),
      });
      if (res && res.ok) { setSelectedId(null); setPage(0); await Promise.all([loadAlerts(), loadStats()]); }
    } finally { setBusyBulk(false); }
  };

  const c = (k) => (stats ? stats[k] ?? 0 : 0);
  const FILTERS = [
    { id: "tous", label: "Toutes", n: c("total") },
    { id: "new", label: "Nouvelles", n: c("new") },
    { id: "acknowledged", label: "Acquittées", n: c("acknowledged") },
    { id: "resolved", label: "Résolues", n: c("resolved") },
  ];
  const selected = alerts.find((a) => a.id === selectedId) || alerts[0] || null;
  const alertsCount = c("new");
  const total = statusFilter === "tous" ? c("total") : c(statusFilter);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <OsShell alertsCount={alertsCount}>
      <div className="p-6">
        <div className="flex items-end justify-between gap-4 mb-5">
          <div>
            <h1 className="text-[22px] font-bold text-os-t1">Centre d&apos;alertes</h1>
            <p className="text-[13px] text-os-t3 mt-0.5">Traitez les alertes déclenchées par le systeme</p>
          </div>
          <div className="flex items-center gap-2">
            {canResolve && statusFilter !== "resolved" && bulkTarget > 0 && (
              <button onClick={resolveAll} disabled={busyBulk}
                title={statusFilter === "tous" ? "Résoudre toutes les alertes non résolues" : `Résoudre les alertes « ${STATUS_META[statusFilter]?.label || statusFilter} »`}
                className="px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] font-semibold text-os-t2 hover:text-os-t1 inline-flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                <CheckCheck className="h-4 w-4" /> {busyBulk ? "Résolution…" : "Tout résoudre"}
                <span className="os-num text-[11px] opacity-70">{bulkTarget}</span>
              </button>
            )}
            <div className="inline-flex items-center gap-1 rounded-os border border-os-border bg-os-card p-1">
              {FILTERS.map((f) => (
                <button key={f.id} onClick={() => { setStatusFilter(f.id); setPage(0); setSelectedId(null); }}
                  className={`rounded-os px-3 py-1.5 text-[13px] font-medium inline-flex items-center gap-1.5 ${statusFilter === f.id ? "bg-os-primary text-os-on-primary" : "text-os-t3 hover:text-os-t1"}`}>
                  {f.label} <span className="os-num text-[11px] opacity-70">{f.n}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4">
          <div className="space-y-2.5">
            {loading ? (
              <div className="rounded-os-lg border border-os-border bg-os-card py-14 text-center text-[13px] text-os-t3">Chargement…</div>
            ) : alerts.length === 0 ? (
              <div className="rounded-os-lg border border-os-border bg-os-card py-14 text-center">
                <Inbox className="h-9 w-9 mx-auto mb-3 text-os-t4" strokeWidth={1.6} />
                <p className="text-[13px] text-os-t3">Aucune alerte {statusFilter !== "tous" ? "dans ce statut" : "pour le moment"}.</p>
              </div>
            ) : (
              alerts.map((a) => {
                const st = STATUS_META[a.status] || STATUS_META.new;
                const delivery = deliveryMeta(a);
                const active = selected && selected.id === a.id;
                return (
                  <button key={a.id} onClick={() => setSelectedId(a.id)}
                    className={`w-full text-left relative rounded-os-lg border bg-os-card pl-4 pr-4 py-3.5 overflow-hidden transition-colors ${active ? "border-os-border-2" : "border-os-border hover:border-os-border-2"}`}>
                    <span className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: st.color }} />
                    <div className="flex items-center gap-3">
                      <span className="shrink-0 h-12 w-12 rounded-os bg-os-card-2 border border-os-border-2 overflow-hidden grid place-items-center text-os-t4 text-[9px]">
                        {snap(a.snapshot_url) ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={snap(a.snapshot_url)} alt="" className="h-full w-full object-cover" />
                        ) : "SNAPSHOT"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: SEV_COLOR[a.severity] || "var(--os-red)" }}>{KIND_LABEL[a.kind] || a.kind}</span>
                          <span className="text-[11px] font-semibold" style={{ color: st.color }}>· {st.label}</span>
                        </div>
                        <p className="text-[13px] font-semibold text-os-t1 truncate mt-0.5">{a.label}</p>
                        {a.reason && <p className="text-[12px] text-os-t3 truncate">{a.reason}</p>}
                        <p className="text-[11px] truncate mt-0.5" style={{ color: delivery.color }}>{delivery.label}</p>
                      </div>
                      <span className="os-num text-[11px] text-os-t4 shrink-0">{relTime(a.created_at)}</span>
                    </div>
                  </button>
                );
              })
            )}

            {!loading && totalPages > 1 && (
              <div className="flex items-center justify-between pt-1">
                <button onClick={() => { setPage((p) => Math.max(0, p - 1)); setSelectedId(null); }} disabled={page === 0}
                  className="px-3 py-1.5 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5">
                  <ChevronLeft className="h-4 w-4" /> Précédent
                </button>
                <span className="os-num text-[12px] text-os-t3">Page {page + 1} / {totalPages} · {total} alerte{total > 1 ? "s" : ""}</span>
                <button onClick={() => { setPage((p) => Math.min(totalPages - 1, p + 1)); setSelectedId(null); }} disabled={page >= totalPages - 1}
                  className="px-3 py-1.5 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5">
                  Suivant <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>

          {/* Collé en haut du viewport (16 px de marge) : il n'y a plus de topbar
              de 52 px à compenser. */}
          <div className="xl:sticky xl:top-4 h-fit">
            {!selected ? (
              <div className="rounded-os-lg border border-os-border bg-os-card py-16 text-center text-[13px] text-os-t3">Sélectionnez une alerte.</div>
            ) : (
              <div className="rounded-os-lg border border-os-border bg-os-card overflow-hidden">
                <div className="relative aspect-[16/9] bg-os-card-2 grid place-items-center text-os-t4 text-[11px] overflow-hidden">
                  {snap(selected.snapshot_url) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={snap(selected.snapshot_url)} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="os-num">SNAPSHOT · anonymisé · {clock(selected.created_at)}</span>
                  )}
                  <span className="absolute bottom-2 right-2 os-num text-[11px] bg-black/50 text-white px-2 py-1 rounded-os">{selected.camera_name || `Caméra ${selected.camera_id ?? "?"}`}</span>
                </div>

                <div className="p-5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-semibold uppercase tracking-wide" style={{ color: SEV_COLOR[selected.severity] || "var(--os-red)" }}>{KIND_LABEL[selected.kind] || selected.kind}</span>
                    <span className="os-num text-[12px] text-os-t4">· #{selected.id}</span>
                  </div>
                  <h3 className="text-[18px] font-bold text-os-t1 mt-1">{selected.label}</h3>
                  {selected.reason && <p className="text-[13px] text-os-t3">{selected.reason}</p>}

                  <div className="flex items-center mt-5">
                    {[
                      { label: "Déclenchée", done: true },
                      { label: "Acquittée", done: ["acknowledged", "resolved"].includes(selected.status) },
                      { label: "Résolue", done: selected.status === "resolved" },
                    ].map((s, i, arr) => (
                      <div key={s.label} className={`flex items-center ${i < arr.length - 1 ? "flex-1" : ""}`}>
                        <div className="flex flex-col items-center gap-1.5">
                          <span className={`os-num h-7 w-7 grid place-items-center rounded-full text-[12px] font-semibold ${s.done ? "bg-os-green text-white" : "bg-os-card-2 border border-os-border-2 text-os-t3"}`}>{s.done ? "✓" : i + 1}</span>
                          <span className="text-[11px] text-os-t3">{s.label}</span>
                        </div>
                        {i < arr.length - 1 && <span className={`flex-1 h-px mx-2 mb-5 ${arr[i + 1].done ? "bg-os-green" : "bg-os-border-2"}`} />}
                      </div>
                    ))}
                  </div>

                  <div className="grid grid-cols-2 gap-4 mt-5 pt-4 border-t border-os-border">
                    <Meta label="Caméra" value={selected.camera_name || `Caméra ${selected.camera_id ?? "?"}`} />
                    <Meta label="Déclenchée à" value={clock(selected.created_at)} mono />
                    <Meta label="Traitée par" value={selected.acknowledged_by ? `#${selected.acknowledged_by}` : "—"} />
                    <Meta label="Notification" value={deliveryMeta(selected).label} />
                    {selected.notify_attempts > 0 && <Meta label="Tentatives" value={String(selected.notify_attempts)} mono />}
                    {selected.notify_last_error && <Meta label="Dernière erreur" value={selected.notify_last_error} />}
                  </div>

                  <div className="flex items-center gap-2 mt-5">
                    {selected.status === "new" && (
                      <button onClick={() => doAction(selected, "acknowledge")} disabled={busyId === selected.id}
                        className="flex-1 py-2.5 rounded-os bg-os-cta text-white text-[13px] font-semibold inline-flex items-center justify-center gap-2 hover:bg-os-cta-hover disabled:opacity-40">
                        <Check className="h-4 w-4" /> Acquitter
                      </button>
                    )}
                    {selected.status !== "resolved" && selected.status !== "new" && (
                      <button onClick={() => doAction(selected, "resolve")} disabled={busyId === selected.id}
                        className="flex-1 py-2.5 rounded-os bg-os-cta text-white text-[13px] font-semibold inline-flex items-center justify-center gap-2 hover:bg-os-cta-hover disabled:opacity-40">
                        <Archive className="h-4 w-4" /> Marquer résolue
                      </button>
                    )}
                    {selected.status !== "resolved" && (
                      <button onClick={() => doAction(selected, "notify", { channel: "both" })} disabled={busyId === selected.id || !notifyAvailable}
                        title={notifyAvailable ? "Notifier (email/webhook)" : "Notifications non configurées"}
                        className="px-4 py-2.5 rounded-os border border-os-border text-os-t2 text-[13px] font-semibold inline-flex items-center gap-2 hover:text-os-t1 disabled:opacity-40 disabled:cursor-not-allowed">
                        <Send className="h-4 w-4" /> Notifier
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </OsShell>
  );
}

function Meta({ label, value, mono }) {
  return (
    <div>
      <p className="text-[11px] font-semibold tracking-wide uppercase text-os-t4">{label}</p>
      <p className={`text-[13px] text-os-t1 mt-0.5 ${mono ? "os-num" : ""}`}>{value}</p>
    </div>
  );
}

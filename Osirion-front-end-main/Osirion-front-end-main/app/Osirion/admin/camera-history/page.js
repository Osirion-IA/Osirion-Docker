"use client";

/**
 * Historique caméras — section Configurer (thème clair). Disponibilité (uptime %),
 * déconnexions, temps hors-ligne, reconnexions et journal des transitions, à partir
 * de l'historique persisté (camera_status_event). Filtres période / agence / caméra.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { Gauge, WifiOff, Clock, Activity } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented, EmptyState } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const PERIODS = [{ value: 7, label: "7j" }, { value: 30, label: "30j" }, { value: 90, label: "90j" }];
const STATUS = {
  online: { label: "En ligne", color: "var(--os-green)" },
  connecting: { label: "Connexion…", color: "var(--os-amber)" },
  stalled: { label: "Figée", color: "var(--os-amber)" },
  offline: { label: "Hors ligne", color: "var(--os-red)" },
  stopped: { label: "Arrêtée", color: "var(--os-t4)" },
};
const stMeta = (s) => STATUS[s] || { label: s || "—", color: "var(--os-t4)" };
const fmtDur = (s) => {
  if (!s || s < 1) return "0";
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d} j ${h} h`;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min`;
  return `${Math.round(s)} s`;
};
const fmtDate = (iso) => new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const uptimeColor = (p) => (p == null ? "var(--os-t4)" : p >= 95 ? "var(--os-green)" : p >= 70 ? "var(--os-amber)" : "var(--os-red)");

function Kpi({ label, value, hint, icon: Icon, color }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-os-t3">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-os-t4" strokeWidth={1.8} />}
      </div>
      <p className="os-num mt-2 text-[26px] leading-none font-bold" style={{ color: color || "var(--os-t1)" }}>{value}</p>
      {hint && <p className="text-[12px] text-os-t3 mt-2">{hint}</p>}
    </Card>
  );
}

// Courbes : déconnexions / reconnexions par jour (SVG déformé + survol HTML).
function DailyChart({ daily }) {
  const [hover, setHover] = useState(null);
  const n = daily.length;
  const max = Math.max(1, ...daily.flatMap((d) => [d.disconnections, d.reconnections]));
  const X = (i) => (n <= 1 ? 50 : (i / (n - 1)) * 100);
  const Y = (v) => 100 - (v / max) * 100;
  const line = (k) => daily.map((d, i) => `${i === 0 ? "M" : "L"}${X(i).toFixed(2)},${Y(d[k]).toFixed(2)}`).join(" ");
  const area = (k) => `M0,100 ${daily.map((d, i) => `L${X(i).toFixed(2)},${Y(d[k]).toFixed(2)}`).join(" ")} L100,100 Z`;
  const step = Math.max(1, Math.ceil(n / 8));
  const dl = (iso) => { const [, m, dd] = iso.split("-"); return `${dd}/${m}`; };
  return (
    <div>
      <div className="relative" style={{ height: 200 }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          {[25, 50, 75].map((g) => <line key={g} x1="0" y1={g} x2="100" y2={g} stroke="var(--os-border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
          <path d={area("disconnections")} fill="var(--os-red)" fillOpacity="0.10" />
          <path d={line("disconnections")} fill="none" stroke="var(--os-red)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          <path d={line("reconnections")} fill="none" stroke="var(--os-green)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          {hover != null && <line x1={X(hover)} y1="0" x2={X(hover)} y2="100" stroke="var(--os-t4)" strokeWidth="1" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
        </svg>
        <div className="absolute inset-0 flex">
          {daily.map((_, i) => <div key={i} className="flex-1" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />)}
        </div>
        {hover != null && (
          <div className="pointer-events-none absolute top-1 z-10 rounded-os border border-os-border bg-os-card px-2.5 py-1.5 shadow-sm" style={{ left: `${Math.min(80, Math.max(0, X(hover)))}%` }}>
            <div className="os-num text-[11px] text-os-t3">{dl(daily[hover].date)}</div>
            <div className="flex items-center gap-1.5 text-[12px]"><span className="h-2 w-2 rounded-[2px]" style={{ background: "var(--os-red)" }} /><span className="text-os-t2">Déconnexions</span><span className="os-num font-semibold text-os-t1 ml-auto">{daily[hover].disconnections}</span></div>
            <div className="flex items-center gap-1.5 text-[12px]"><span className="h-2 w-2 rounded-[2px]" style={{ background: "var(--os-green)" }} /><span className="text-os-t2">Reconnexions</span><span className="os-num font-semibold text-os-t1 ml-auto">{daily[hover].reconnections}</span></div>
          </div>
        )}
      </div>
      <div className="mt-1.5 flex justify-between">
        {daily.map((d, i) => <span key={i} className="os-num text-[10px] text-os-t4" style={{ visibility: i % step === 0 || i === n - 1 ? "visible" : "hidden" }}>{dl(d.date)}</span>)}
      </div>
    </div>
  );
}

export default function CameraHistoryPage() {
  const [period, setPeriod] = useState(7);
  const [groupId, setGroupId] = useState("");
  const [camId, setCamId] = useState("");
  const [groups, setGroups] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [g, c] = await Promise.all([fetchWithRefresh("/api/groups"), fetchWithRefresh("/api/cameras")]);
      if (g?.ok) { const d = await g.json(); setGroups(Array.isArray(d) ? d : []); }
      if (c?.ok) { const d = await c.json(); setCameras(Array.isArray(d) ? d : []); }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const qs = new URLSearchParams({ days: String(period) });
    if (camId) qs.set("camera_id", camId);
    else if (groupId) qs.set("group_id", groupId);
    try {
      const [s, h] = await Promise.all([
        fetchWithRefresh(`/api/camera-status/stats?${qs}`),
        fetchWithRefresh(`/api/camera-status/history?${qs}&limit=200`),
      ]);
      setStats(s?.ok ? await s.json() : null);
      setEvents(h?.ok ? (await h.json()).events || [] : []);
    } finally { setLoading(false); }
  }, [period, groupId, camId]);
  useEffect(() => { load(); }, [load]);

  const sum = stats?.summary || {};
  const rows = stats?.cameras || [];
  const camOptions = useMemo(
    () => cameras.filter((c) => !groupId || (c.group_ids || []).includes(Number(groupId))),
    [cameras, groupId]
  );

  const sel = "rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none";

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Historique caméras"
          subtitle="Disponibilité, coupures, reconnexions · historique persisté"
          actions={<Segmented value={period} onChange={setPeriod} options={PERIODS} size="sm" />}
        />

        {/* Filtres */}
        <div className="mb-5 flex flex-wrap items-center gap-2">
          <select value={groupId} onChange={(e) => { setGroupId(e.target.value); setCamId(""); }} className={sel}>
            <option value="">Toutes les agences</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <select value={camId} onChange={(e) => setCamId(e.target.value)} className={sel}>
            <option value="">Toutes les caméras</option>
            {camOptions.map((c) => <option key={c.id} value={c.id}>{c.cam_name || `Caméra ${c.id}`}</option>)}
          </select>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <Kpi label="Disponibilité moyenne" icon={Gauge}
            value={loading ? "—" : sum.avg_uptime_pct != null ? `${sum.avg_uptime_pct}%` : "—"}
            color={uptimeColor(sum.avg_uptime_pct)}
            hint={`${sum.cameras ?? 0} caméra(s) suivie(s)`} />
          <Kpi label="Déconnexions" icon={WifiOff}
            value={loading ? "—" : (sum.total_disconnections ?? 0)}
            hint={`sur ${period} j`} />
          <Kpi label="Hors ligne maintenant" icon={Activity}
            value={loading ? "—" : (sum.currently_offline ?? 0)}
            color={sum.currently_offline > 0 ? "var(--os-red)" : "var(--os-green)"}
            hint={`/ ${sum.cameras ?? 0} caméra(s)`} />
          <Kpi label="Temps hors-ligne cumulé" icon={Clock}
            value={loading ? "—" : fmtDur(sum.total_offline_seconds)}
            hint="toutes caméras" />
        </div>

        {/* Connectivité par jour (courbes) */}
        {stats?.daily?.length > 0 && (
          <Card className="p-5 mb-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[15px] font-semibold text-os-t1">Connectivité par jour</h3>
              <div className="flex items-center gap-4 text-[12px] text-os-t3">
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: "var(--os-red)" }} />Déconnexions</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: "var(--os-green)" }} />Reconnexions</span>
              </div>
            </div>
            <DailyChart daily={stats.daily} />
          </Card>
        )}

        {/* Disponibilité par caméra */}
        <Card className="p-5 mb-4">
          <h3 className="text-[15px] font-semibold text-os-t1 mb-4">Disponibilité par caméra</h3>
          {rows.length === 0 ? (
            <EmptyState icon={Activity}>Aucun historique sur la période. Les transitions d&apos;état s&apos;accumulent au fil du temps.</EmptyState>
          ) : (
            <div className="space-y-3.5">
              {rows.map((c) => {
                const m = stMeta(c.current_status);
                return (
                  <div key={c.camera_id}>
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2 min-w-0 text-[13px]">
                        <span className="h-2 w-2 rounded-full shrink-0" style={{ background: m.color }} />
                        <span className="truncate text-os-t1">{c.name}</span>
                        {c.site && <span className="text-os-t4 shrink-0">· {c.site}</span>}
                      </span>
                      <span className="os-num shrink-0 font-semibold" style={{ color: uptimeColor(c.uptime_pct) }}>
                        {c.uptime_pct != null ? `${c.uptime_pct}%` : "—"}
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-os-border-2">
                      <div className="h-full rounded-full" style={{ width: `${c.uptime_pct ?? 0}%`, background: uptimeColor(c.uptime_pct) }} />
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-os-t3">
                      <span>{c.disconnections} déconnexion(s)</span>
                      <span>{c.reconnections} reconnexion(s)</span>
                      <span>hors-ligne {fmtDur(c.offline_seconds)}</span>
                      <span>plus longue coupure {fmtDur(c.longest_outage_seconds)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Journal des transitions */}
        <Card className="p-5">
          <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Journal des transitions ({events.length})</h3>
          {events.length === 0 ? (
            <p className="text-[13px] text-os-t3 py-6 text-center">Aucune transition sur la période.</p>
          ) : (
            <ul className="divide-y divide-os-border max-h-[420px] overflow-y-auto">
              {events.map((e) => {
                const to = stMeta(e.status), from = stMeta(e.prev_status);
                return (
                  <li key={e.id} className="flex items-center gap-3 py-2 text-[13px]">
                    <span className="os-num text-[11px] text-os-t4 w-24 shrink-0">{fmtDate(e.timestamp)}</span>
                    <span className="min-w-0 flex-1 truncate text-os-t1">{e.name}{e.site ? <span className="text-os-t4"> · {e.site}</span> : null}</span>
                    <span className="shrink-0 inline-flex items-center gap-1.5">
                      {e.prev_status && <><span className="text-[11px]" style={{ color: from.color }}>{from.label}</span><span className="text-os-t4">→</span></>}
                      <span className="inline-flex items-center gap-1 text-[12px] font-medium" style={{ color: to.color }}>
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: to.color }} />{to.label}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </OsShell>
  );
}

"use client";

/**
 * Cockpit — écran d'accueil de la section Surveiller (thème sombre).
 * Objectif produit : répondre en 3 s à « tout va bien ? », par site si besoin.
 *
 * 100 % anonyme. Filtres AGENCE / CAMÉRA qui scopent tout le tableau. Câblé aux
 * vraies données : summary/occupancy (analytics), queue-performance (files P90/SLA),
 * camera-status/stats (disponibilité), zones, alerts, cameras, rules.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw, Users, ArrowUp, Clock, X, ArrowRight, Wifi } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const ONB_KEY = "osirion-cockpit-onboarding";
const POLL_MS = 8000;

const j = async (r) => (r && r.ok ? r.json().catch(() => null) : null);
const num = (n) => (typeof n === "number" && isFinite(n) ? n : 0);
const pct = (n, d) => (d > 0 ? Math.round((100 * n) / d) : 0);
function fmtWait(sec) {
  sec = Math.round(num(sec));
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m} min ${String(s).padStart(2, "0")} s`;
}
function ago(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith?.("Z") ? iso : `${iso}Z`);
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 45) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return d.toLocaleDateString("fr-FR");
}
function loadColor(frac) {
  if (frac < 0.6) return "var(--os-green)";
  if (frac < 0.85) return "var(--os-amber)";
  return "var(--os-red)";
}
const upColor = (p) => (p == null ? "var(--os-t4)" : p >= 95 ? "var(--os-green)" : p >= 70 ? "var(--os-amber)" : "var(--os-red)");
const SEV_COLOR = { info: "var(--os-blue)", warning: "var(--os-amber)", critical: "var(--os-red)" };
const dateFr = () => new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

function Kpi({ label, value, sub, icon: Icon, accent, color }) {
  return (
    <div className="rounded-os-lg border border-os-border bg-os-card p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-os-t3">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-os-t4" strokeWidth={1.9} />}
      </div>
      <p className="os-num mt-3 text-[34px] leading-none font-bold" style={{ color: color || "var(--os-t1)" }}>{value}</p>
      {sub && <p className={`mt-2 text-[12px] ${accent || "text-os-t3"}`}>{sub}</p>}
    </div>
  );
}

function Donut({ frac }) {
  const r = 26, C = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, frac || 0));
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" className="shrink-0 -rotate-90">
      <circle cx="32" cy="32" r={r} fill="none" stroke="var(--os-border-2)" strokeWidth="7" />
      <circle cx="32" cy="32" r={r} fill="none" stroke={loadColor(f)} strokeWidth="7" strokeLinecap="round"
        strokeDasharray={C} strokeDashoffset={C * (1 - f)} style={{ transition: "stroke-dashoffset .6s ease, stroke .3s" }} />
    </svg>
  );
}

export default function CockpitPage() {
  const [data, setData] = useState(null);
  const [clock, setClock] = useState("");
  const [onbDismissed, setOnbDismissed] = useState(true);
  const [groupId, setGroupId] = useState("");
  const [camId, setCamId] = useState("");
  const [groups, setGroups] = useState([]);

  useEffect(() => {
    try { setOnbDismissed(localStorage.getItem(ONB_KEY) === "1"); } catch { /* */ }
    fetchWithRefresh("/api/groups").then(j).then((g) => setGroups(Array.isArray(g) ? g : []));
  }, []);

  // Données de CONFIG (zones, caméras, règles) : quasi statiques → chargées au
  // montage puis rafraîchies lentement. Inutile de les re-télécharger toutes les 8 s.
  const loadStatic = useCallback(async () => {
    const [zones, cams, rules] = await Promise.all([
      fetchWithRefresh("/api/zones").then(j),
      fetchWithRefresh("/api/cameras").then(j),
      fetchWithRefresh("/api/rules").then(j),
    ]);
    setData((d) => ({
      ...d,
      zones: Array.isArray(zones) ? zones : [],
      cams: Array.isArray(cams) ? cams : [],
      rulesCount: (Array.isArray(rules) ? rules : []).length,
    }));
  }, []);

  // Données LIVE : 1 appel AGRÉGÉ (résumé + occupation + files + dispo) + alertes.
  // Remplace 6 requêtes par 2 ; le backend sert le tout depuis un cache court.
  const loadLive = useCallback(async () => {
    const f = camId ? `camera_id=${camId}` : groupId ? `group_id=${groupId}` : "";
    const fq = f ? `?${f}` : "";
    const [agg, alerts] = await Promise.all([
      fetchWithRefresh(`/api/analytics/cockpit${fq}`).then(j),
      fetchWithRefresh("/api/alerts?status=new").then(j),
    ]);
    setData((d) => ({
      ...d,
      summary: agg?.summary || {},
      occByZone: Object.fromEntries((agg?.occupancy?.zones || []).map((z) => [z.zone_id, z.count])),
      camStats: agg?.camera_status || {},
      queues: agg?.queue_performance?.queues || [],
      alerts: Array.isArray(alerts) ? alerts : alerts?.alerts || [],
    }));
  }, [groupId, camId]);

  useEffect(() => {
    loadStatic();
    const t = setInterval(loadStatic, 60000);
    return () => clearInterval(t);
  }, [loadStatic]);

  useEffect(() => {
    loadLive();
    const t = setInterval(loadLive, POLL_MS);
    return () => clearInterval(t);
  }, [loadLive]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }));
    tick();
    const t = setInterval(tick, 15000);
    return () => clearInterval(t);
  }, []);

  const d = data;
  const s = d?.summary || {};
  const filtered = !!(groupId || camId);

  // Scope AGENCE / CAMÉRA appliqué côté client aux caméras/zones/alertes.
  const camsAll = d?.cams || [];
  const inScope = (c) => (camId ? c.id === Number(camId) : groupId ? (c.group_ids || []).includes(Number(groupId)) : true);
  const cams = camsAll.filter(inScope);
  const scopeIds = new Set(cams.map((c) => c.id));
  const camsOnline = cams.filter((c) => c.is_active).length;

  const alerts = filtered ? (d?.alerts || []).filter((a) => a.camera_id != null && scopeIds.has(a.camera_id)) : (d?.alerts || []);
  const alertsCount = alerts.length;

  const cs = d?.camStats?.summary || {};                 // disponibilité (Phase 1)
  const queues = d?.queues || [];                         // files avec P90 (Phase 2)
  const occZones = (d?.zones || []).filter((z) => (z.kind === "occupancy" || z.kind === "generic") && scopeIds.has(z.camera_id));
  const totalCap = occZones.reduce((a, z) => a + (z.threshold || 0), 0);
  const occTotalPct = pct(num(s.current_occupancy), totalCap);

  const ok = alertsCount === 0 && !(cs.currently_offline > 0);
  const dismissOnb = () => { try { localStorage.setItem(ONB_KEY, "1"); } catch { /* */ } setOnbDismissed(true); };

  const onbSteps = [
    { n: 1, title: "Ajouter une caméra", desc: "Connectez un flux à votre site.", done: camsAll.length > 0 },
    { n: 2, title: "Dessiner une zone", desc: "Tracez zones et lignes de comptage.", done: (d?.zones?.length || 0) > 0 },
    { n: 3, title: "Créer une règle", desc: "Définissez seuils et plages horaires.", done: (d?.rulesCount || 0) > 0 },
    { n: 4, title: "Recevoir des alertes", desc: "Email / webhook sur événement.", done: (d?.alerts?.length || 0) > 0 },
  ];

  const camOptions = camsAll.filter((c) => !groupId || (c.group_ids || []).includes(Number(groupId)));
  const sel = "rounded-os border border-os-border bg-os-card px-3 py-1.5 text-[12px] text-os-t2 outline-none";

  return (
    <OsShell alertsCount={alertsCount} camsOnline={camsOnline} camsTotal={cams.length}>
      <div className="p-6 space-y-6 max-w-[1600px]">
        {!onbDismissed && (
          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-[16px] font-semibold text-os-t1">Mettez votre site en service</h3>
                <p className="text-[13px] text-os-t3 mt-0.5">4 étapes pour transformer vos caméras en capteurs de flux anonymes.</p>
              </div>
              <button onClick={dismissOnb} className="text-os-t4 hover:text-os-t1 p-1" aria-label="Masquer"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              {onbSteps.map((st) => (
                <div key={st.n} className="rounded-os border p-3.5"
                  style={st.done ? { borderColor: "rgba(31,170,89,.4)", background: "rgba(31,170,89,.06)" } : { borderColor: "var(--os-border-2)" }}>
                  <div className="flex items-center gap-2.5">
                    <span className={`os-num h-6 w-6 grid place-items-center rounded-full text-[12px] font-semibold ${st.done ? "bg-os-green text-white" : "bg-os-cta text-os-t2"}`}>{st.done ? "✓" : st.n}</span>
                    <span className="text-[13px] font-medium text-os-t1">{st.title}</span>
                  </div>
                  <p className="text-[12px] text-os-t3 mt-2 leading-snug">{st.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold text-os-t1">Cockpit</h1>
            <p className="text-[13px] text-os-t3 mt-0.5 capitalize">{dateFr()}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select value={groupId} onChange={(e) => { setGroupId(e.target.value); setCamId(""); }} className={sel}>
              <option value="">Toutes les agences</option>
              {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
            <select value={camId} onChange={(e) => setCamId(e.target.value)} className={sel}>
              <option value="">Toutes les caméras</option>
              {camOptions.map((c) => <option key={c.id} value={c.id}>{c.cam_name || `Caméra ${c.id}`}</option>)}
            </select>
            <span className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-os border border-os-border bg-os-card">
              <span className="h-2 w-2 rounded-full bg-os-red os-anim-blink" />
              <span className="text-[12px] font-semibold text-os-t2">LIVE</span>
              <span className="os-num text-[12px] text-os-t3">{clock}</span>
            </span>
            <button onClick={() => { loadStatic(); loadLive(); }} className="h-9 w-9 grid place-items-center rounded-os border border-os-border bg-os-card text-os-t3 hover:text-os-t1" aria-label="Rafraîchir"><RefreshCw className="h-4 w-4" /></button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
          <div className="xl:col-span-1 rounded-os-lg border p-5"
            style={ok ? { borderColor: "rgba(31,170,89,.4)", background: "rgba(31,170,89,.05)" } : { borderColor: "rgba(245,166,35,.4)", background: "rgba(245,166,35,.06)" }}>
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-os-green" : "bg-os-amber"}`} />
              <span className="text-[11px] font-semibold tracking-[0.12em] uppercase text-os-t3">État du site</span>
            </div>
            <p className={`mt-3 text-[26px] leading-tight font-bold ${ok ? "text-os-green" : "text-os-amber"}`}>{ok ? "Tout va bien" : "Attention requise"}</p>
            <p className="text-[13px] text-os-t3 mt-1">
              {alertsCount > 0 ? `${alertsCount} alerte${alertsCount > 1 ? "s" : ""} à traiter` : cs.currently_offline > 0 ? `${cs.currently_offline} caméra(s) hors ligne` : "Aucune alerte active"}
            </p>
            <div className="mt-4 flex flex-wrap items-end gap-x-5 gap-y-2">
              <div><p className="os-num text-[18px] font-bold text-os-t1">{camsOnline}/{cams.length}</p><p className="text-[11px] text-os-t3">caméras</p></div>
              <div><p className="os-num text-[18px] font-bold" style={{ color: upColor(cs.avg_uptime_pct) }}>{cs.avg_uptime_pct != null ? `${cs.avg_uptime_pct}%` : "—"}</p><p className="text-[11px] text-os-t3">dispo. 24 h</p></div>
              <div><p className="os-num text-[18px] font-bold text-os-t1">{occTotalPct}%</p><p className="text-[11px] text-os-t3">occupation</p></div>
              <div><p className="os-num text-[18px] font-bold text-os-t1">{alertsCount}</p><p className="text-[11px] text-os-t3">alertes</p></div>
            </div>
          </div>
          <Kpi label="Présents" icon={Users} value={num(s.present_now_estimate)} sub={s.present_source === "occupancy" ? "dans les zones suivies" : "estimation (entrées − sorties)"} />
          <Kpi label="Entrées" icon={ArrowUp} value={num(s.entries_today)} sub="aujourd'hui" accent="text-os-green" />
          <Kpi label="Caméras hors ligne" icon={Wifi} value={num(cs.currently_offline)} color={cs.currently_offline > 0 ? "var(--os-red)" : "var(--os-green)"} sub={`/ ${cs.cameras ?? cams.length} suivie(s)`} />
          <Kpi label="Attente des clients" icon={Clock} value={queues.length ? fmtWait(queues[0]?.wait_avg_s) : "—"} sub={queues.length ? `9 clients sur 10 sous ${fmtWait(queues[0]?.wait_p90_s)}` : "aucune file"} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Occupation des zones</h3>
              <Link href="/Osirion/admin/zones" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Gérer <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {occZones.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune zone d&apos;occupation sur ce périmètre.</p>
            ) : (
              <div className="space-y-4">
                {occZones.slice(0, 4).map((z) => {
                  const count = num(d.occByZone?.[z.id]); const cap = z.threshold || 0; const frac = cap > 0 ? count / cap : 0;
                  return (
                    <div key={z.id} className="flex items-center gap-4">
                      <Donut frac={frac} />
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-semibold text-os-t1 truncate">{z.name}</p>
                        <p className="os-num text-[12px] text-os-t3">{count}{cap ? ` / ${cap} places` : ""}</p>
                      </div>
                      {cap > 0 && <span className="os-num text-[20px] font-bold" style={{ color: loadColor(frac) }}>{pct(count, cap)}%</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Files d&apos;attente</h3>
              <Link href="/Osirion/admin/analytics" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Analyser <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {queues.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune file sur ce périmètre.</p>
            ) : (
              <div className="space-y-5">
                {queues.slice(0, 3).map((q) => {
                  const over = q.over_threshold_pct > 0;
                  const frac = Math.min(1, q.length > 0 ? q.length / Math.max(q.length, 8) : 0);
                  return (
                    <div key={q.zone_id}>
                      <div className="flex items-baseline justify-between">
                        <p className="text-[14px] font-semibold text-os-t1 truncate">{q.name}{q.site ? <span className="text-os-t4 font-normal"> · {q.site}</span> : null}</p>
                        <span className={`os-num text-[20px] font-bold ${over ? "text-os-red" : "text-os-t1"}`}>{num(q.length)}</span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-os-border-2 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${frac * 100}%`, background: over ? "var(--os-red)" : "var(--os-green)", transition: "width .5s ease" }} />
                      </div>
                      <div className="mt-1.5 flex justify-between os-num text-[11px] text-os-t3">
                        <span>Attente {fmtWait(q.wait_avg_s)} · 9/10 sous {fmtWait(q.wait_p90_s)}</span>
                        {q.over_threshold_pct != null && <span style={{ color: over ? "var(--os-amber)" : undefined }}>{q.over_threshold_pct}% trop longue</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Alertes en cours</h3>
              <Link href="/Osirion/admin/alerts" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Centre <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {alertsCount === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune alerte active. Tout va bien.</p>
            ) : (
              <ul className="space-y-2.5">
                {alerts.slice(0, 5).map((a) => (
                  <li key={a.id} className="rounded-os border border-os-border pl-3 pr-3 py-2.5 relative overflow-hidden">
                    <span className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: SEV_COLOR[a.severity] || "var(--os-red)" }} />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold tracking-wide uppercase" style={{ color: SEV_COLOR[a.severity] || "var(--os-red)" }}>Nouvelle</span>
                      <span className="os-num text-[11px] text-os-t4">{ago(a.created_at)}</span>
                    </div>
                    <p className="text-[13px] font-semibold text-os-t1 mt-0.5 truncate">{a.label || a.kind}</p>
                    {a.reason && <p className="text-[12px] text-os-t3 truncate">{a.reason}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="rounded-os-lg border border-os-border bg-os-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-semibold text-os-t1">Parc caméras{filtered ? " (filtré)" : ""}</h3>
            <Link href="/Osirion/admin/camera-history" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Historique <ArrowRight className="h-3.5 w-3.5" /></Link>
          </div>
          {cams.length === 0 ? (
            <p className="text-[13px] text-os-t3 py-4 text-center">Aucune caméra sur ce périmètre.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
              {cams.slice(0, 6).map((c) => (
                <div key={c.id} className="rounded-os border border-os-border-2 p-3">
                  <div className="flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${c.is_active ? "bg-os-green" : "bg-os-t4"}`} />
                    <span className="text-[12px] text-os-t3">{c.is_active ? "En ligne" : "Inactive"}</span>
                  </div>
                  <p className="text-[13px] font-semibold text-os-t1 mt-1.5 truncate">{c.cam_name || `Caméra ${c.id}`}</p>
                  <p className="os-num text-[11px] text-os-t4 truncate">{c.location || "—"}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </OsShell>
  );
}

"use client";

/**
 * Cockpit — écran d'accueil de la section Surveiller (thème sombre).
 * Objectif produit : répondre en 3 s à « tout va bien ? ».
 *
 * 100 % anonyme : présents, entrées/sorties, occupation, files, alertes — jamais
 * d'identité. Câblé aux vraies données backend via les proxies /api/* existants :
 *   summary/occupancy/queues (analytics), zones, alerts?status=new, cameras, rules.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw, Users, ArrowUp, ArrowDown, Clock, X, ArrowRight } from "lucide-react";
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
const SEV_COLOR = { info: "var(--os-blue)", warning: "var(--os-amber)", critical: "var(--os-red)" };
const dateFr = () =>
  new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });

function Kpi({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="rounded-os-lg border border-os-border bg-os-card p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-os-t3">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-os-t4" strokeWidth={1.9} />}
      </div>
      <p className="os-num mt-3 text-[34px] leading-none font-bold text-os-t1">{value}</p>
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
      <circle
        cx="32" cy="32" r={r} fill="none" stroke={loadColor(f)} strokeWidth="7" strokeLinecap="round"
        strokeDasharray={C} strokeDashoffset={C * (1 - f)}
        style={{ transition: "stroke-dashoffset .6s ease, stroke .3s" }}
      />
    </svg>
  );
}

export default function CockpitPage() {
  const [data, setData] = useState(null);
  const [clock, setClock] = useState("");
  const [onbDismissed, setOnbDismissed] = useState(true);

  useEffect(() => {
    try { setOnbDismissed(localStorage.getItem(ONB_KEY) === "1"); } catch { /* */ }
  }, []);

  const load = useCallback(async () => {
    const [summary, occ, queues, zones, alerts, cams, rules] = await Promise.all([
      fetchWithRefresh("/api/analytics/summary").then(j),
      fetchWithRefresh("/api/analytics/occupancy").then(j),
      fetchWithRefresh("/api/analytics/queues").then(j),
      fetchWithRefresh("/api/zones").then(j),
      fetchWithRefresh("/api/alerts?status=new").then(j),
      fetchWithRefresh("/api/cameras").then(j),
      fetchWithRefresh("/api/rules").then(j),
    ]);
    const alertList = Array.isArray(alerts) ? alerts : alerts?.alerts || [];
    setData({
      summary: summary || {},
      occByZone: Object.fromEntries((occ?.zones || []).map((z) => [z.zone_id, z.count])),
      queues: queues?.queues || [],
      zones: Array.isArray(zones) ? zones : [],
      alerts: alertList,
      cams: Array.isArray(cams) ? cams : [],
      rulesCount: (Array.isArray(rules) ? rules : []).length,
    });
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }));
    tick();
    const t = setInterval(tick, 15000);
    return () => clearInterval(t);
  }, []);

  const d = data;
  const s = d?.summary || {};
  const cams = d?.cams || [];
  const camsOnline = cams.filter((c) => c.is_active).length;
  const alertsCount = d?.alerts?.length || 0;

  // Zones d'occupation (avec seuil = capacité de référence).
  const occZones = (d?.zones || []).filter((z) => z.kind === "occupancy" || z.kind === "generic");
  const totalCap = occZones.reduce((a, z) => a + (z.threshold || 0), 0);
  const occTotalPct = pct(num(s.current_occupancy), totalCap);

  const ok = alertsCount === 0;
  const dismissOnb = () => { try { localStorage.setItem(ONB_KEY, "1"); } catch { /* */ } setOnbDismissed(true); };

  const onbSteps = [
    { n: 1, title: "Ajouter une caméra", desc: "Connectez un flux RTSP à votre site.", done: cams.length > 0 },
    { n: 2, title: "Dessiner une zone", desc: "Tracez zones et lignes de comptage sur la vidéo.", done: (d?.zones?.length || 0) > 0 },
    { n: 3, title: "Créer une règle", desc: "Définissez seuils et plages horaires.", done: (d?.rulesCount || 0) > 0 },
    { n: 4, title: "Recevoir des alertes", desc: "Email / webhook sur événement.", done: alertsCount > 0 },
  ];

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
              <button onClick={dismissOnb} className="text-os-t4 hover:text-os-t1 p-1" aria-label="Masquer">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              {onbSteps.map((st) => (
                <div key={st.n} className="rounded-os border p-3.5"
                  style={st.done ? { borderColor: "rgba(31,170,89,.4)", background: "rgba(31,170,89,.06)" } : { borderColor: "var(--os-border-2)" }}>
                  <div className="flex items-center gap-2.5">
                    <span className={`os-num h-6 w-6 grid place-items-center rounded-full text-[12px] font-semibold ${st.done ? "bg-os-green text-white" : "bg-os-cta text-os-t2"}`}>
                      {st.done ? "✓" : st.n}
                    </span>
                    <span className="text-[13px] font-medium text-os-t1">{st.title}</span>
                  </div>
                  <p className="text-[12px] text-os-t3 mt-2 leading-snug">{st.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold text-os-t1">Cockpit</h1>
            <p className="text-[13px] text-os-t3 mt-0.5 capitalize">{dateFr()}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-os border border-os-border bg-os-card">
              <span className="h-2 w-2 rounded-full bg-os-red os-anim-blink" />
              <span className="text-[12px] font-semibold text-os-t2">LIVE</span>
              <span className="os-num text-[12px] text-os-t3">{clock}</span>
            </span>
            <button onClick={load} className="h-9 w-9 grid place-items-center rounded-os border border-os-border bg-os-card text-os-t3 hover:text-os-t1" aria-label="Rafraîchir">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
          <div className="xl:col-span-1 rounded-os-lg border p-5"
            style={ok
              ? { borderColor: "rgba(31,170,89,.4)", background: "rgba(31,170,89,.05)" }
              : { borderColor: "rgba(245,166,35,.4)", background: "rgba(245,166,35,.06)" }}>

            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-os-green" : "bg-os-amber"}`} />
              <span className="text-[11px] font-semibold tracking-[0.12em] uppercase text-os-t3">État du site</span>
            </div>
            <p className={`mt-3 text-[26px] leading-tight font-bold ${ok ? "text-os-green" : "text-os-amber"}`}>
              {ok ? "Tout va bien" : "Attention requise"}
            </p>
            <p className="text-[13px] text-os-t3 mt-1">
              {ok ? "Aucune alerte active" : `${alertsCount} alerte${alertsCount > 1 ? "s" : ""} à traiter`}
            </p>
            <div className="mt-4 flex items-end gap-5">
              <div><p className="os-num text-[18px] font-bold text-os-t1">{camsOnline}/{cams.length}</p><p className="text-[11px] text-os-t3">caméras</p></div>
              <div><p className="os-num text-[18px] font-bold text-os-t1">{occTotalPct}%</p><p className="text-[11px] text-os-t3">occupation</p></div>
              <div><p className="os-num text-[18px] font-bold text-os-t1">{alertsCount}</p><p className="text-[11px] text-os-t3">alertes</p></div>
            </div>
          </div>
          <Kpi label="Présents" icon={Users} value={num(s.present_now_estimate)} sub="personnes maintenant" />
          <Kpi label="Entrées" icon={ArrowUp} value={num(s.entries_today)} sub="aujourd'hui" accent="text-os-green" />
          <Kpi label="Sorties" icon={ArrowDown} value={num(s.exits_today)} sub="aujourd'hui" />
          <Kpi label="Attente moy." icon={Clock} value={fmtWait(s.avg_wait_s)} sub="toutes files" />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Occupation des zones</h3>
              <Link href="/Osirion/admin/zones" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Gérer <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {occZones.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune zone d&apos;occupation configurée.</p>
            ) : (
              <div className="space-y-4">
                {occZones.slice(0, 4).map((z) => {
                  const count = num(d.occByZone[z.id]);
                  const cap = z.threshold || 0;
                  const frac = cap > 0 ? count / cap : 0;
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
              <span className="os-num text-[11px] text-os-t4">temps réel</span>
            </div>
            {(d?.queues?.length || 0) === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune file configurée.</p>
            ) : (
              <div className="space-y-5">
                {d.queues.slice(0, 3).map((q) => {
                  const thr = (d.zones.find((z) => z.id === q.zone_id) || {}).threshold || 0;
                  const over = thr > 0 && q.length >= thr;
                  const frac = thr > 0 ? Math.min(1, q.length / thr) : (q.length > 0 ? 1 : 0);
                  return (
                    <div key={q.zone_id}>
                      <div className="flex items-baseline justify-between">
                        <p className="text-[14px] font-semibold text-os-t1">{q.name}</p>
                        <span className={`os-num text-[20px] font-bold ${over ? "text-os-red" : "text-os-t1"}`}>{num(q.length)}</span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-os-border-2 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${frac * 100}%`, background: over ? "var(--os-red)" : "var(--os-green)", transition: "width .5s ease" }} />
                      </div>
                      <div className="mt-1.5 flex justify-between os-num text-[11px] text-os-t3">
                        <span>Attente moy. {fmtWait(q.wait_avg_s)}</span>
                        <span>Max {fmtWait(q.wait_max_s)}</span>
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
                {d.alerts.slice(0, 5).map((a) => (
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
            <h3 className="text-[15px] font-semibold text-os-t1">Parc caméras</h3>
            <Link href="/Osirion/admin/live" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Mur de caméras <ArrowRight className="h-3.5 w-3.5" /></Link>
          </div>
          {cams.length === 0 ? (
            <p className="text-[13px] text-os-t3 py-4 text-center">Aucune caméra configurée.</p>
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

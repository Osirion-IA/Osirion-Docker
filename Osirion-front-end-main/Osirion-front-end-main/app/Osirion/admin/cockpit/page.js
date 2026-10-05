"use client";

/**
 * Cockpit — écran d'accueil de la section Surveiller.
 * Objectif produit : répondre en 3 s à « tout va bien ? », par site si besoin.
 *
 * 100 % anonyme. Filtres AGENCE / CAMÉRA appliqués côté serveur.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw, Clock, X, ArrowRight, Wifi, Activity } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { fmtWait, relative, dayLong } from "../../../lib/format";

const ONB_KEY = "osirion-cockpit-onboarding";
// Synthèse servie par un cache serveur de 5 min — repoller plus vite ne rendrait
// pas la réponse plus fraîche. Le temps réel passe par Socket.IO.
const POLL_MS = 60000;
const STATIC_POLL_MS = 300000;
const ALERTS_PREVIEW = 5;

const j = async (r) => (r && r.ok ? r.json().catch(() => null) : null);
const num = (n) => (typeof n === "number" && isFinite(n) ? n : 0);
function loadColor(frac) {
  if (frac < 0.6) return "var(--os-green)";
  if (frac < 0.85) return "var(--os-amber)";
  return "var(--os-red)";
}
const upColor = (p) => (p == null ? "var(--os-t4)" : p >= 95 ? "var(--os-green)" : p >= 70 ? "var(--os-amber)" : "var(--os-red)");
// `reason` répète souvent `label` (« Saturation de file d'attente » sous
// « Saturation de file d'attente — FA (14 pers.) ») : on ne l'affiche que s'il
// apporte autre chose.
const distinctReason = (alert) => {
  const reason = (alert?.reason || "").trim();
  const label = (alert?.label || "").trim();
  if (!reason || !label) return reason || "";
  const norm = (t) => t.toLowerCase().replace(/\s+/g, " ");
  return norm(label).includes(norm(reason)) ? "" : reason;
};

const SEV_COLOR = { info: "var(--os-blue)", warning: "var(--os-amber)", critical: "var(--os-red)" };

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

export default function CockpitPage() {
  const [data, setData] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [onbDismissed, setOnbDismissed] = useState(true);
  const [groupId, setGroupId] = useState("");
  const [camId, setCamId] = useState("");
  const [groups, setGroups] = useState([]);

  useEffect(() => {
    try { setOnbDismissed(localStorage.getItem(ONB_KEY) === "1"); } catch { /* */ }
    fetchWithRefresh("/api/groups").then(j).then((g) => setGroups(Array.isArray(g) ? g : []));
  }, []);

  // Config quasi statique : sélecteurs de filtre, seuils de files, onboarding.
  // Une caméra ajoutée à chaud apparaît au tour suivant ou au clic sur Rafraîchir.
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

  // Le compte d'alertes vient de /stats, pas de la longueur de la liste : celle-ci
  // est paginée et plafonnerait le chiffre à la taille de page.
  const loadLive = useCallback(async () => {
    const f = camId ? `camera_id=${camId}` : groupId ? `group_id=${groupId}` : "";
    const fq = f ? `?${f}` : "";
    const [agg, alerts, alertStats] = await Promise.all([
      fetchWithRefresh(`/api/analytics/cockpit${fq}`).then(j),
      fetchWithRefresh(`/api/alerts?status=new&limit=${ALERTS_PREVIEW}${f ? `&${f}` : ""}`).then(j),
      fetchWithRefresh(`/api/alerts/stats${fq}`).then(j),
    ]);
    setData((d) => ({
      ...d,
      camStats: agg?.camera_status || {},
      queues: agg?.queue_performance?.queues || [],
      alerts: Array.isArray(alerts) ? alerts : alerts?.alerts || [],
      alertsNew: num(alertStats?.new),
    }));
    setUpdatedAt(new Date());
  }, [groupId, camId]);

  useEffect(() => {
    loadStatic();
    const t = setInterval(loadStatic, STATIC_POLL_MS);
    return () => clearInterval(t);
  }, [loadStatic]);

  useEffect(() => {
    loadLive();
    const t = setInterval(loadLive, POLL_MS);
    return () => clearInterval(t);
  }, [loadLive]);

  const d = data;
  const camsAll = d?.cams || [];
  const alerts = d?.alerts || [];
  const alertsCount = num(d?.alertsNew);

  const cs = d?.camStats?.summary || {};
  const queues = d?.queues || [];
  const offline = num(cs.currently_offline);
  const monitored = num(cs.cameras);
  const zoneThreshold = Object.fromEntries((d?.zones || []).map((z) => [z.id, z.threshold || 0]));
  const slowest = queues[0] || null;

  const ok = alertsCount === 0 && offline === 0;
  const dismissOnb = () => { try { localStorage.setItem(ONB_KEY, "1"); } catch { /* */ } setOnbDismissed(true); };

  const onbSteps = [
    { n: 1, title: "Ajouter une caméra", desc: "Connectez un flux à votre site.", done: camsAll.length > 0 },
    { n: 2, title: "Dessiner une zone", desc: "Tracez zones et lignes de comptage.", done: (d?.zones?.length || 0) > 0 },
    { n: 3, title: "Créer une règle", desc: "Définissez seuils et plages horaires.", done: (d?.rulesCount || 0) > 0 },
    { n: 4, title: "Recevoir des alertes", desc: "Email / webhook sur événement.", done: alertsCount > 0 },
  ];

  // Une fois les 4 étapes faites, le bloc n'a plus rien à apprendre : il
  // disparaît sans attendre un clic sur la croix.
  const onbComplete = onbSteps.every((st) => st.done);

  const camOptions = camsAll.filter((c) => !groupId || (c.group_ids || []).includes(Number(groupId)));
  const sel = "rounded-os border border-os-border bg-os-card px-3 py-1.5 text-[12px] text-os-t2 outline-none";

  return (
    <OsShell alertsCount={alertsCount}>
      <div className="p-6 space-y-6 max-w-[1600px]">
        {!onbDismissed && !onbComplete && (
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
            <p className="text-[13px] text-os-t3 mt-0.5 capitalize">{dayLong()}</p>
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
              <span className="text-[12px] text-os-t3">
                Actualisé {updatedAt ? updatedAt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "…"}
              </span>
            </span>
            <button onClick={() => { loadStatic(); loadLive(); }} className="h-9 w-9 grid place-items-center rounded-os border border-os-border bg-os-card text-os-t3 hover:text-os-t1" aria-label="Rafraîchir"><RefreshCw className="h-4 w-4" /></button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          <div className="rounded-os-lg border p-5"
            style={ok ? { borderColor: "rgba(31,170,89,.4)", background: "rgba(31,170,89,.05)" } : { borderColor: "rgba(245,166,35,.4)", background: "rgba(245,166,35,.06)" }}>
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-os-green" : "bg-os-amber"}`} />
              <span className="text-[11px] font-semibold tracking-[0.12em] uppercase text-os-t3">État du site</span>
            </div>
            <p className={`mt-3 text-[26px] leading-tight font-bold ${ok ? "text-os-green" : "text-os-amber"}`}>{ok ? "Tout va bien" : "Attention requise"}</p>
            <p className="text-[13px] text-os-t3 mt-1">
              {alertsCount > 0
                ? `${alertsCount} alerte${alertsCount > 1 ? "s" : ""} à traiter`
                : offline > 0
                  ? `${offline} caméra${offline > 1 ? "s" : ""} hors ligne`
                  : "Aucune alerte active"}
            </p>
          </div>

          <Kpi
            label="Caméras hors ligne" icon={Wifi} value={offline}
            color={offline > 0 ? "var(--os-red)" : "var(--os-green)"}
            sub={monitored ? `sur ${monitored} caméra${monitored > 1 ? "s" : ""} supervisée${monitored > 1 ? "s" : ""}` : "aucune caméra supervisée"}
          />
          <Kpi
            label="Disponibilité 24 h" icon={Activity}
            value={cs.avg_uptime_pct != null ? `${cs.avg_uptime_pct}%` : "—"}
            color={upColor(cs.avg_uptime_pct)}
            sub="moyenne des caméras supervisées"
          />
          <Kpi
            label="Attente la plus longue" icon={Clock}
            value={slowest ? fmtWait(slowest.wait_avg_s) : "—"}
            sub={slowest ? `${slowest.name} · 9 clients sur 10 sous ${fmtWait(slowest.wait_p90_s)}` : "aucune file"}
          />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Files d&apos;attente</h3>
              <Link href="/Osirion/admin/analytics" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Analyser <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {queues.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune file sur ce périmètre.</p>
            ) : (
              <div className="space-y-5">
                {queues.slice(0, 4).map((q) => {
                  const cap = zoneThreshold[q.zone_id] || 0;
                  const len = num(q.length);
                  const frac = cap > 0 ? Math.min(1, len / cap) : 0;
                  const over = cap > 0 && len >= cap;
                  return (
                    <div key={q.zone_id}>
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="text-[14px] font-semibold text-os-t1 truncate">{q.name}{q.site ? <span className="text-os-t4 font-normal"> · {q.site}</span> : null}</p>
                        <span className={`os-num text-[20px] font-bold shrink-0 ${over ? "text-os-red" : "text-os-t1"}`}>
                          {len}{cap ? <span className="text-[13px] font-normal text-os-t3"> / {cap}</span> : null}
                        </span>
                      </div>
                      {cap > 0 && (
                        <div className="mt-2 h-2 rounded-full bg-os-border-2 overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${frac * 100}%`, background: loadColor(frac), transition: "width .5s ease" }} />
                        </div>
                      )}
                      <div className="mt-1.5 os-num text-[11px] text-os-t3">
                        Attente {fmtWait(q.wait_avg_s)} · 9 clients sur 10 sous {fmtWait(q.wait_p90_s)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-os-lg border border-os-border bg-os-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">
                Alertes en cours
                {alertsCount > ALERTS_PREVIEW && <span className="ml-2 os-num text-[12px] font-normal text-os-t3">{ALERTS_PREVIEW} plus récentes sur {alertsCount}</span>}
              </h3>
              <Link href="/Osirion/admin/alerts" className="text-[12px] text-os-t3 hover:text-os-t1 inline-flex items-center gap-1">Centre <ArrowRight className="h-3.5 w-3.5" /></Link>
            </div>
            {alerts.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune alerte active. Tout va bien.</p>
            ) : (
              <ul className="space-y-2.5">
                {alerts.slice(0, ALERTS_PREVIEW).map((a) => (
                  <li key={a.id} className="rounded-os border border-os-border pl-3 pr-3 py-2.5 relative overflow-hidden">
                    <span className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: SEV_COLOR[a.severity] || "var(--os-red)" }} />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold tracking-wide uppercase" style={{ color: SEV_COLOR[a.severity] || "var(--os-red)" }}>Nouvelle</span>
                      <span className="os-num text-[11px] text-os-t4">{relative(a.created_at)}</span>
                    </div>
                    <p className="text-[13px] font-semibold text-os-t1 mt-0.5 truncate">{a.label || a.kind}</p>
                    {distinctReason(a) && <p className="text-[12px] text-os-t3 truncate">{distinctReason(a)}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </OsShell>
  );
}

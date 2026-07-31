"use client";

/**
 * Analytique — tendances de flux ANONYMES exploitables pour la décision (section
 * Analyser, thème clair). Couvre le TEMPOREL (tendance journalière, profil horaire,
 * heatmap, prévision), le SPATIAL (sites & caméras), l'OPÉRATIONNEL (files,
 * occupation) et la SÉCURITÉ (incidents & alertes). Prévisions = base statistique
 * historique (pas de ML). Données : /analytics/{insights,footfall,queues,occupancy,
 * by-camera,incidents}.
 */
import { useState, useEffect, useCallback } from "react";
import { TrendingUp, Clock, CalendarDays, Sparkles, ArrowUp, ArrowDown, Download, MapPin, ShieldAlert } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const WD = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const WD_LONG = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
const BIZ = Array.from({ length: 17 }, (_, i) => i + 6); // 6h..22h
const hLabel = (h) => `${h}h`;
const fmtWait = (s) => (!s ? "0 s" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
const dLabel = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const PERIODS = [{ value: 7, label: "7j" }, { value: 30, label: "30j" }, { value: 90, label: "90j" }];
const TABS = [
  { value: "affluence", label: "Affluence" },
  { value: "sites", label: "Sites & caméras" },
  { value: "queues", label: "Files & attente" },
  { value: "occupancy", label: "Occupation" },
  { value: "incidents", label: "Incidents" },
];

function Insight({ label, value, hint, icon: Icon, trend }) {
  const tColor = trend == null ? "text-os-t3" : trend >= 0 ? "text-os-green" : "text-os-red";
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-os-t3">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-os-t4" strokeWidth={1.8} />}
      </div>
      <p className="os-num mt-2 text-[26px] leading-none font-bold text-os-t1">{value}</p>
      {hint && (
        <p className={`text-[12px] mt-2 inline-flex items-center gap-1 ${tColor}`}>
          {trend != null && (trend >= 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
          {hint}
        </p>
      )}
    </Card>
  );
}

// Légende (identité de série jamais par la couleur seule → pastille + libellé).
function Legend({ items }) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5 text-[12px] text-os-t3">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: it.color }} />{it.label}
        </span>
      ))}
    </div>
  );
}

// Graphe temporel multi-séries (change-over-time → lignes + aire). SVG déformé
// (preserveAspectRatio none) avec traits à épaisseur constante ; libellés et survol
// en HTML par-dessus. keys=[{k,label,color,fill?}].
function TrendChart({ series, keys, height = 230 }) {
  const [hover, setHover] = useState(null);
  const n = series.length;
  const max = Math.max(1, ...series.flatMap((s) => keys.map((k) => s[k.k] || 0)));
  const X = (i) => (n <= 1 ? 50 : (i / (n - 1)) * 100);
  const Y = (v) => 100 - (v / max) * 100;
  const line = (k) => series.map((s, i) => `${i === 0 ? "M" : "L"}${X(i).toFixed(2)},${Y(s[k] || 0).toFixed(2)}`).join(" ");
  const area = (k) => `M0,100 ${series.map((s, i) => `L${X(i).toFixed(2)},${Y(s[k] || 0).toFixed(2)}`).join(" ")} L100,100 Z`;
  const step = Math.max(1, Math.ceil(n / 8));
  return (
    <div>
      <div className="relative" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          {[25, 50, 75].map((g) => <line key={g} x1="0" y1={g} x2="100" y2={g} stroke="var(--os-border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
          {keys.filter((k) => k.fill).map((k) => <path key={`a${k.k}`} d={area(k.k)} fill={k.color} fillOpacity="0.12" />)}
          {keys.map((k) => <path key={k.k} d={line(k.k)} fill="none" stroke={k.color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />)}
          {hover != null && <line x1={X(hover)} y1="0" x2={X(hover)} y2="100" stroke="var(--os-t4)" strokeWidth="1" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
        </svg>
        {/* colonnes de survol */}
        <div className="absolute inset-0 flex">
          {series.map((s, i) => (
            <div key={i} className="flex-1" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          ))}
        </div>
        {hover != null && (
          <div className="pointer-events-none absolute top-1 z-10 rounded-os border border-os-border bg-os-card px-2.5 py-1.5 shadow-sm"
            style={{ left: `${Math.min(80, Math.max(0, X(hover)))}%` }}>
            <div className="os-num text-[11px] text-os-t3">{dLabel(series[hover].date)}</div>
            {keys.map((k) => (
              <div key={k.k} className="flex items-center gap-1.5 text-[12px]">
                <span className="h-2 w-2 rounded-[2px]" style={{ background: k.color }} />
                <span className="text-os-t2">{k.label}</span>
                <span className="os-num font-semibold text-os-t1 ml-auto">{series[hover][k.k] || 0}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="mt-1.5 flex justify-between">
        {series.map((s, i) => (
          <span key={i} className="os-num text-[10px] text-os-t4" style={{ visibility: i % step === 0 || i === n - 1 ? "visible" : "hidden" }}>{dLabel(s.date)}</span>
        ))}
      </div>
    </div>
  );
}

// Barres horizontales classées (magnitude → une seule teinte séquentielle).
function RankBars({ rows, valueKey, labelKey, subKey, color = "var(--os-cta)", fmt = (v) => v }) {
  const max = Math.max(1, ...rows.map((r) => r[valueKey] || 0));
  return (
    <div className="space-y-3">
      {rows.map((r, i) => (
        <div key={r.camera_id ?? r.site ?? i}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate text-os-t1">{r[labelKey] || "—"}{subKey && r[subKey] ? <span className="text-os-t4"> · {r[subKey]}</span> : null}</span>
            <span className="os-num shrink-0 font-semibold text-os-t1">{fmt(r[valueKey] || 0)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-os-border-2">
            <div className="h-full rounded-full" style={{ width: `${((r[valueKey] || 0) / max) * 100}%`, background: color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function HourlyBars({ hourly, peakHour }) {
  const rows = BIZ.map((h) => hourly.find((x) => x.hour === h) || { hour: h, entries: 0 });
  const max = Math.max(1, ...rows.map((r) => r.entries));
  return (
    <div className="flex items-end gap-2 h-56">
      {rows.map((r) => {
        const isPeak = r.hour === peakHour;
        return (
          <div key={r.hour} className="flex-1 flex flex-col items-center gap-1.5 min-w-0">
            <span className="os-num text-[10px] text-os-t3">{r.entries || ""}</span>
            <div className="w-full flex items-end justify-center flex-1">
              <div className="w-full max-w-[26px] rounded-t-os" title={`${hLabel(r.hour)} · ${r.entries}`}
                style={{ height: `${Math.max(2, (r.entries / max) * 100)}%`, background: isPeak ? "var(--os-cta)" : "var(--os-border-2)" }} />
            </div>
            <span className="os-num text-[10px] text-os-t4">{hLabel(r.hour)}</span>
          </div>
        );
      })}
    </div>
  );
}

function Heatmap({ matrix, max }) {
  const cell = (v) => {
    const a = max > 0 ? 0.06 + 0.94 * (v / max) : 0.04;
    return `rgba(47,127,209,${a.toFixed(3)})`;
  };
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px]">
        <div className="flex pl-9">
          {BIZ.map((h) => <div key={h} className="flex-1 text-center os-num text-[9px] text-os-t4">{h}</div>)}
        </div>
        {matrix.map((row, wd) => (
          <div key={wd} className="flex items-center mt-1">
            <div className="w-9 text-[11px] text-os-t3">{WD[wd]}</div>
            {BIZ.map((h) => (
              <div key={h} className="flex-1 px-0.5">
                <div className="h-5 rounded-[2px]" title={`${WD[wd]} ${h}h · ${row[h]}`} style={{ background: cell(row[h]) }} />
              </div>
            ))}
          </div>
        ))}
        <div className="flex items-center gap-2 mt-3 pl-9">
          <span className="text-[11px] text-os-t4">Faible</span>
          <div className="h-2 flex-1 rounded-full" style={{ background: "linear-gradient(90deg, rgba(47,127,209,0.06), rgba(47,127,209,1))" }} />
          <span className="text-[11px] text-os-t4">Fort</span>
        </div>
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const [period, setPeriod] = useState(30);
  const [tab, setTab] = useState("affluence");
  const [groupId, setGroupId] = useState("");
  const [camId, setCamId] = useState("");
  const [groups, setGroups] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [ins, setIns] = useState(null);
  const [foot, setFoot] = useState(null);
  const [qaff, setQaff] = useState(null);       // affluence basée files (queue-affluence)
  const [qperf, setQperf] = useState(null);     // performance files (queue-performance)
  const [occZones, setOccZones] = useState([]);
  const [byCam, setByCam] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [g, c] = await Promise.all([fetchWithRefresh("/api/groups"), fetchWithRefresh("/api/cameras")]);
      if (g?.ok) { const x = await g.json(); setGroups(Array.isArray(x) ? x : []); }
      if (c?.ok) { const x = await c.json(); setCameras(Array.isArray(x) ? x : []); }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams();
    if (camId) p.set("camera_id", camId);
    else if (groupId) p.set("group_id", groupId);
    const fq = p.toString() ? `&${p}` : "";
    try {
      const hours = period * 24;
      const [i, f, qa, qp, o, bc, inc] = await Promise.all([
        fetchWithRefresh(`/api/analytics/insights?days=${period}`),
        fetchWithRefresh(`/api/analytics/footfall?days=${period}${camId ? `&camera_id=${camId}` : ""}`),
        fetchWithRefresh(`/api/analytics/queue-affluence?days=${period}${fq}`),
        fetchWithRefresh(`/api/analytics/queue-performance?days=${Math.min(period, 90)}${fq}`),
        fetchWithRefresh(`/api/analytics/occupancy?hours=${hours}`),
        fetchWithRefresh(`/api/analytics/by-camera?days=${Math.min(period, 90)}`),
        fetchWithRefresh(`/api/analytics/incidents?days=${Math.min(period, 90)}`),
      ]);
      setIns(i?.ok ? await i.json() : null);
      setFoot(f?.ok ? await f.json() : null);
      setQaff(qa?.ok ? await qa.json() : null);
      setQperf(qp?.ok ? await qp.json() : null);
      setOccZones(o?.ok ? (await o.json()).zones || [] : []);
      setByCam(bc?.ok ? await bc.json() : null);
      setIncidents(inc?.ok ? await inc.json() : null);
    } finally { setLoading(false); }
  }, [period, groupId, camId]);
  useEffect(() => { load(); }, [load]);

  const d = ins || {};
  const today = d.today || {};
  const hasData = (d.total_entries || 0) > 0;
  const maxOcc = Math.max(1, ...occZones.map((z) => z.count || 0));

  // Affluence basée FILES (queue-affluence) — le pic vient de l'OCCUPATION des files,
  // pas des entrées/sorties.
  const qa = qaff || {};
  const qPeak = qa.peak_hour;
  const hasQueues = !!qa.has_queues;
  const agencies = qperf?.agencies || [];
  const fmtWaitShort = (s) => (!s ? "0 s" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min`);

  const recos = [];
  if (hasQueues && qPeak != null) recos.push(`Affluence maximale des files vers ${qPeak}h–${qPeak + 1}h (occupation moyenne ${qa.peak_avg_occupancy}). Renforcez les guichets sur ce créneau.`);
  if (hasQueues && qa.quietest_hour != null) recos.push(`Files les plus calmes vers ${qa.quietest_hour}h — fenêtre idéale pour la maintenance ou les pauses.`);
  if (agencies.length) { const w = agencies[0]; recos.push(`Agence à la plus forte attente : ${w.site} — moyenne ${fmtWaitShort(w.wait_avg_s)}, P90 ${fmtWaitShort(w.wait_p90_s)}.`); }
  if (hasData && today.vs_avg_pct != null) recos.push(today.vs_avg_pct >= 0
    ? `Aujourd'hui +${today.vs_avg_pct}% de passages vs d'habitude — anticipez une journée chargée.`
    : `Aujourd'hui ${today.vs_avg_pct}% vs d'habitude — plus calme que la normale.`);

  // Export CSV de la tendance journalière (entrées/sorties/net).
  const exportCsv = () => {
    const rows = foot?.series || [];
    if (!rows.length) return;
    const csv = ["date,entrees,sorties,net", ...rows.map((r) => `${r.date},${r.entries},${r.exits},${r.net}`)].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a");
    a.href = url; a.download = `affluence_${period}j.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const deltaEntries = foot?.delta_entries_pct;

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Analytique"
          subtitle="Tendances de flux anonymes · aide à la décision"
          actions={
            <div className="flex items-center gap-2">
              <button onClick={exportCsv} disabled={!foot?.series?.length}
                className="h-9 px-3 inline-flex items-center gap-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-40">
                <Download className="h-4 w-4" /> CSV
              </button>
              <Segmented value={period} onChange={setPeriod} options={PERIODS} size="sm" />
            </div>
          }
        />

        {d.confidence && d.confidence !== "high" && hasData && (
          <div className="mb-4 rounded-os border border-os-border bg-os-card px-4 py-2.5 text-[12px] text-os-t3">
            ⓘ Historique {d.confidence === "low" ? "limité" : "partiel"} ({d.active_days} jour(s) de données) — les projections et prévisions s&apos;affineront à mesure que l&apos;historique s&apos;accumule.
          </div>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <select value={groupId} onChange={(e) => { setGroupId(e.target.value); setCamId(""); }}
            className="rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none">
            <option value="">Toutes les agences</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <select value={camId} onChange={(e) => setCamId(e.target.value)}
            className="rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none">
            <option value="">Toutes les caméras</option>
            {cameras.filter((c) => !groupId || (c.group_ids || []).includes(Number(groupId))).map((c) => <option key={c.id} value={c.id}>{c.cam_name || `Caméra ${c.id}`}</option>)}
          </select>
          <span className="text-[11px] text-os-t4">Filtres appliqués à l&apos;affluence des files et aux files &amp; attente.</span>
        </div>

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <Insight label="Aujourd'hui" icon={TrendingUp}
            value={loading ? "—" : (today.so_far ?? 0)}
            hint={hasData && today.projected_eod ? `projeté ~${today.projected_eod}${today.vs_avg_pct != null ? ` · ${today.vs_avg_pct >= 0 ? "+" : ""}${today.vs_avg_pct}% vs moy.` : ""}` : "passages entrants"}
            trend={today.vs_avg_pct} />
          <Insight label={`Entrées · ${period}j`} icon={TrendingUp}
            value={loading ? "—" : (foot?.total_entries ?? 0)}
            hint={deltaEntries != null ? `${deltaEntries >= 0 ? "+" : ""}${deltaEntries}% vs période préc.` : "période précédente vide"}
            trend={deltaEntries} />
          <Insight label="Pic des files" icon={Clock}
            value={loading ? "—" : qPeak != null ? `${qPeak}h–${qPeak + 1}h` : "—"}
            hint={qPeak != null ? `occ. moy. ${qa.peak_avg_occupancy}` : hasQueues ? "pas encore de pic" : "aucune file"} />
          <Insight label="Attente — top agence" icon={CalendarDays}
            value={loading ? "—" : agencies.length ? fmtWaitShort(agencies[0].wait_avg_s) : "—"}
            hint={agencies.length ? `${agencies[0].site} · P90 ${fmtWaitShort(agencies[0].wait_p90_s)}` : "aucune file"} />
        </div>

        <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>

        {tab === "affluence" && (
          !hasData && !hasQueues ? (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucune donnée. Dessinez une <b>zone « file d&apos;attente »</b> (pour l&apos;affluence des files) ou une <b>ligne de comptage</b> dans « Zones », et activez une caméra.</p></Card>
          ) : (
            <div className="space-y-4">
              <Card className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-[15px] font-semibold text-os-t1">Tendance journalière</h3>
                  <Legend items={[{ label: "Entrées", color: "var(--os-cta)" }, { label: "Sorties", color: "var(--os-t3)" }]} />
                </div>
                {foot?.series?.length ? (
                  <TrendChart series={foot.series} keys={[
                    { k: "entries", label: "Entrées", color: "var(--os-cta)", fill: true },
                    { k: "exits", label: "Sorties", color: "var(--os-t3)" },
                  ]} />
                ) : <p className="text-[13px] text-os-t3 py-8 text-center">Pas encore de série journalière.</p>}
              </Card>

              <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-4">
                <Card className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[15px] font-semibold text-os-t1">Occupation des files par heure</h3>
                    <span className="os-num text-[12px] text-os-t3">{qa.queues || 0} file(s)</span>
                  </div>
                  {hasQueues ? (
                    <HourlyBars hourly={(qa.hourly || []).map((x) => ({ hour: x.hour, entries: x.avg_occupancy }))} peakHour={qPeak} />
                  ) : <p className="text-[13px] text-os-t3 py-10 text-center">Aucune file configurée (zone « file d&apos;attente »).</p>}
                </Card>

                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Prévision — prochaines heures</h3>
                  <p className="text-[12px] text-os-t3 mb-3">Attendu d&apos;après un {WD_LONG[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1]} habituel.</p>
                  {d.forecast?.length ? (
                    <div className="flex items-end gap-3">
                      {d.forecast.map((f) => {
                        const fmax = Math.max(1, ...d.forecast.map((x) => x.expected));
                        return (
                          <div key={f.hour} className="flex-1 flex flex-col items-center gap-1.5">
                            <span className="os-num text-[13px] font-bold text-os-t1">~{f.expected}</span>
                            <div className="w-full flex items-end justify-center h-20">
                              <div className="w-8 rounded-t-os" style={{ height: `${Math.max(6, (f.expected / fmax) * 100)}%`, background: "var(--os-blue)", opacity: 0.55 }} />
                            </div>
                            <span className="os-num text-[11px] text-os-t3">{f.hour}h</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : <p className="text-[13px] text-os-t3 py-6 text-center">Hors plage horaire de fréquentation.</p>}
                </Card>
              </div>

              {recos.length > 0 && (
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-3 inline-flex items-center gap-2"><Sparkles className="h-4 w-4 text-os-blue" /> Recommandations</h3>
                  <ul className="space-y-2.5">
                    {recos.map((r, i) => (
                      <li key={i} className="flex gap-2.5 text-[13px] text-os-t2">
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-os-blue shrink-0" />{r}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {qa.busiest_periods?.length > 0 && (
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Moments de forte affluence</h3>
                  <p className="text-[12px] text-os-t3 mb-3">Créneaux (jour × heure) où les files ont été les plus chargées</p>
                  <ul className="space-y-2">
                    {qa.busiest_periods.map((p, i) => (
                      <li key={i} className="flex items-center justify-between gap-3 rounded-os border border-os-border px-3 py-2 text-[13px]">
                        <span className="text-os-t1">{new Date(p.date).toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "short" })} · {p.hour}h–{p.hour + 1}h</span>
                        <span className="os-num font-semibold text-os-t1">occ. moyenne {p.avg_occupancy}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <Card className="p-5">
                <h3 className="text-[15px] font-semibold text-os-t1">Carte de chaleur — files</h3>
                <p className="text-[12px] text-os-t3 mb-4">Occupation moyenne des files par jour de semaine et par heure</p>
                <Heatmap matrix={qa.heatmap || []} max={qa.heatmap_max || 0} />
              </Card>
            </div>
          )
        )}

        {tab === "sites" && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card className="p-5">
              <h3 className="text-[15px] font-semibold text-os-t1 mb-1 inline-flex items-center gap-2"><MapPin className="h-4 w-4 text-os-t4" /> Sites les plus fréquentés</h3>
              <p className="text-[12px] text-os-t3 mb-4">Entrées cumulées par site sur {Math.min(period, 90)} j</p>
              {byCam?.sites?.length ? (
                <RankBars rows={byCam.sites} valueKey="entries" labelKey="site" subKey="cameras"
                  fmt={(v) => v.toLocaleString("fr-FR")} />
              ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucune donnée de site.</p>}
            </Card>
            <Card className="p-5">
              <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Caméras les plus fréquentées</h3>
              <p className="text-[12px] text-os-t3 mb-4">Entrées par caméra (occupation courante à droite)</p>
              {byCam?.cameras?.length ? (
                <div className="space-y-3">
                  {(() => { const max = Math.max(1, ...byCam.cameras.map((c) => c.entries || 0)); return byCam.cameras.map((c) => (
                    <div key={c.camera_id}>
                      <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                        <span className="truncate text-os-t1">{c.name}{c.site ? <span className="text-os-t4"> · {c.site}</span> : null}</span>
                        <span className="shrink-0 os-num text-os-t1 font-semibold">{c.entries}<span className="text-os-t4 font-normal"> ent.</span>{c.current_occupancy ? <span className="text-os-t3 font-normal"> · {c.current_occupancy} présents</span> : null}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-os-border-2">
                        <div className="h-full rounded-full" style={{ width: `${((c.entries || 0) / max) * 100}%`, background: "var(--os-cta)" }} />
                      </div>
                    </div>
                  )); })()}
                </div>
              ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucune donnée de caméra. Activez des caméras et tracez des lignes de comptage.</p>}
            </Card>
          </div>
        )}

        {tab === "queues" && (
          <div className="space-y-4">
            <Card className="p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-[15px] font-semibold text-os-t1">Files & attente</h3>
                {qperf?.wait_threshold_s ? <span className="text-[12px] text-os-t3">seuil SLA {fmtWait(qperf.wait_threshold_s)}</span> : null}
              </div>
              {!qperf?.queues?.length ? (
                <p className="text-[13px] text-os-t3 py-8 text-center">Aucune zone de type « file » sur ce périmètre. Créez-en une dans « Zones ».</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px] min-w-[560px]">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-os-t3 border-b border-os-border">
                        <th className="py-2.5 font-semibold">File</th>
                        <th className="py-2.5 font-semibold text-right">Long.</th>
                        <th className="py-2.5 font-semibold text-right">Attente moy.</th>
                        <th className="py-2.5 font-semibold text-right">P90</th>
                        <th className="py-2.5 font-semibold text-right">Max</th>
                        <th className="py-2.5 font-semibold text-right">&gt; seuil</th>
                      </tr>
                    </thead>
                    <tbody>
                      {qperf.queues.map((q) => (
                        <tr key={q.zone_id} className="border-b border-os-border last:border-0">
                          <td className="py-2.5 text-os-t1">{q.name}{q.site ? <span className="text-os-t4"> · {q.site}</span> : null}</td>
                          <td className="py-2.5 os-num text-os-t1 text-right font-semibold">{q.length}</td>
                          <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_avg_s)}</td>
                          <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_p90_s)}</td>
                          <td className="py-2.5 os-num text-os-t3 text-right">{fmtWait(q.wait_max_s)}</td>
                          <td className="py-2.5 os-num text-right" style={{ color: q.over_threshold_pct > 20 ? "var(--os-red)" : q.over_threshold_pct > 0 ? "var(--os-amber)" : "var(--os-t3)" }}>{q.over_threshold_pct == null ? "—" : `${q.over_threshold_pct}%`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {agencies.length > 0 && (
              <Card className="p-5">
                <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Classement des agences — temps d&apos;attente</h3>
                <p className="text-[12px] text-os-t3 mb-4">Attente moyenne par agence · P90 = 9 clients sur 10 servis en dessous</p>
                <div className="space-y-3">
                  {(() => { const max = Math.max(1, ...agencies.map((a) => a.wait_avg_s)); return agencies.map((a) => (
                    <div key={a.site}>
                      <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                        <span className="truncate text-os-t1">{a.site}</span>
                        <span className="shrink-0 os-num text-os-t1 font-semibold">{fmtWait(a.wait_avg_s)}<span className="text-os-t4 font-normal"> · P90 {fmtWait(a.wait_p90_s)} · {a.over_threshold_pct}% &gt; seuil</span></span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-os-border-2">
                        <div className="h-full rounded-full" style={{ width: `${(a.wait_avg_s / max) * 100}%`, background: "var(--os-cta)" }} />
                      </div>
                    </div>
                  )); })()}
                </div>
              </Card>
            )}
          </div>
        )}

        {tab === "occupancy" && (
          <Card className="p-5">
            <h3 className="text-[15px] font-semibold text-os-t1 mb-4">Occupation par zone</h3>
            {occZones.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-8 text-center">Aucune occupation récente. Dessinez des zones et activez une caméra.</p>
            ) : (
              <div className="space-y-3">
                {occZones.map((z) => (
                  <div key={z.zone_id}>
                    <div className="flex items-center justify-between text-[13px] mb-1">
                      <span className="text-os-t1">{z.zone_name || `Zone ${z.zone_id}`}</span>
                      <span className="os-num text-os-t1 font-semibold">{z.count}</span>
                    </div>
                    <div className="h-2 rounded-full bg-os-border-2 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${(z.count / maxOcc) * 100}%`, background: "var(--os-blue)" }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {tab === "incidents" && (
          (incidents?.alerts_total || incidents?.crowd_total) ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <Insight label="Alertes" icon={ShieldAlert} value={incidents.alerts_total} hint={`sur ${Math.min(period, 90)} j`} />
                <Insight label="Attroupements" icon={ShieldAlert} value={incidents.crowd_total} hint="détections CROWD" />
                <Insight label="Critiques" icon={ShieldAlert} value={incidents.by_severity.critical}
                  hint={incidents.by_severity.warning ? `+ ${incidents.by_severity.warning} avert.` : "aucune"} />
                <Insight label="Taux de résolution" icon={ShieldAlert}
                  value={incidents.resolution_rate != null ? `${incidents.resolution_rate}%` : "—"}
                  hint={`${incidents.by_status.resolved} résolue(s) / ${incidents.alerts_total}`} />
              </div>

              <Card className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-[15px] font-semibold text-os-t1">Incidents par jour</h3>
                  <Legend items={[{ label: "Alertes", color: "var(--os-amber)" }, { label: "Attroupements", color: "var(--os-red)" }]} />
                </div>
                <TrendChart series={incidents.series} keys={[
                  { k: "alerts", label: "Alertes", color: "var(--os-amber)", fill: true },
                  { k: "crowd", label: "Attroupements", color: "var(--os-red)" },
                ]} />
              </Card>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-4">Par sévérité</h3>
                  {(() => {
                    const sev = [
                      { label: "Critique", v: incidents.by_severity.critical, c: "var(--os-red)" },
                      { label: "Avertissement", v: incidents.by_severity.warning, c: "var(--os-amber)" },
                      { label: "Info", v: incidents.by_severity.info, c: "var(--os-blue)" },
                    ];
                    const max = Math.max(1, ...sev.map((s) => s.v));
                    return (
                      <div className="space-y-3">
                        {sev.map((s) => (
                          <div key={s.label}>
                            <div className="mb-1 flex items-center justify-between text-[13px]">
                              <span className="inline-flex items-center gap-1.5 text-os-t1"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: s.c }} />{s.label}</span>
                              <span className="os-num font-semibold text-os-t1">{s.v}</span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-os-border-2">
                              <div className="h-full rounded-full" style={{ width: `${(s.v / max) * 100}%`, background: s.c }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </Card>
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-4">Alertes par caméra</h3>
                  {incidents.by_camera?.length ? (
                    <RankBars rows={incidents.by_camera} valueKey="count" labelKey="name" color="var(--os-amber)" />
                  ) : <p className="text-[13px] text-os-t3 py-6 text-center">Aucune alerte rattachée à une caméra.</p>}
                </Card>
              </div>
            </div>
          ) : (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucun incident sur la période. Les attroupements détectés et les alertes du centre d&apos;alertes apparaîtront ici.</p></Card>
          )
        )}
      </div>
    </OsShell>
  );
}

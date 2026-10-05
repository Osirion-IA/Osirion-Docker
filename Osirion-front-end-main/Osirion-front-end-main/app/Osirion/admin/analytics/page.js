"use client";

/**
 * Analytique — tendances de flux ANONYMES exploitables pour la décision (section
 * Analyser, thème clair). Couvre le TEMPOREL (tendance journalière, profil horaire,
 * heatmap, prévision), le SPATIAL (sites & caméras), l'OPÉRATIONNEL (files,
 * occupation) et la SÉCURITÉ (incidents & alertes). Prévisions = base statistique
 * historique (pas de ML). Données : /analytics/{insights,footfall,queues,occupancy,
 * by-camera,incidents,post-absence,staffing}.
 */
import { useState, useEffect, useCallback } from "react";
import { TrendingUp, Clock, CalendarDays, Sparkles, ArrowUp, ArrowDown, Download, MapPin, ShieldAlert } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented, SkeletonKpis } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { fmtWait, fmtDuration } from "../../../lib/format";

const WD = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const WD_LONG = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
const BIZ = Array.from({ length: 17 }, (_, i) => i + 6); // 6h..22h
const hLabel = (h) => `${h}h`;
const dLabel = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const PERIODS = [{ value: 7, label: "7j" }, { value: 30, label: "30j" }, { value: 90, label: "90j" }];
const TABS = [
  { value: "affluence", label: "Affluence" },
  { value: "sites", label: "Sites & caméras" },
  { value: "queues", label: "Files & attente" },
  { value: "occupancy", label: "Occupation" },
  { value: "presence", label: "Présence & effectifs" },
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
        <div key={r.zone_id ?? r.camera_id ?? r.site ?? i}>
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
  const [absence, setAbsence] = useState(null);
  const [staffing, setStaffing] = useState(null);
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
      const [i, f, qa, qp, o, bc, inc, pa, st] = await Promise.all([
        fetchWithRefresh(`/api/analytics/insights?days=${period}${fq}`),
        fetchWithRefresh(`/api/analytics/footfall?days=${period}${fq}`),
        fetchWithRefresh(`/api/analytics/queue-affluence?days=${period}${fq}`),
        fetchWithRefresh(`/api/analytics/queue-performance?days=${Math.min(period, 90)}${fq}`),
        fetchWithRefresh(`/api/analytics/occupancy?hours=${hours}${fq}`),
        fetchWithRefresh(`/api/analytics/by-camera?days=${Math.min(period, 90)}${fq}`),
        fetchWithRefresh(`/api/analytics/incidents?days=${Math.min(period, 90)}${fq}`),
        fetchWithRefresh(`/api/analytics/post-absence?days=${period}${fq}`),
        fetchWithRefresh(`/api/analytics/staffing?days=${period}${fq}`),
      ]);
      setIns(i?.ok ? await i.json() : null);
      setFoot(f?.ok ? await f.json() : null);
      setQaff(qa?.ok ? await qa.json() : null);
      setQperf(qp?.ok ? await qp.json() : null);
      setOccZones(o?.ok ? (await o.json()).zones || [] : []);
      setByCam(bc?.ok ? await bc.json() : null);
      setIncidents(inc?.ok ? await inc.json() : null);
      setAbsence(pa?.ok ? await pa.json() : null);
      setStaffing(st?.ok ? await st.json() : null);
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

  const recos = [];
  if (hasQueues && qPeak != null) recos.push(`Affluence maximale des files vers ${qPeak}h–${qPeak + 1}h (occupation moyenne ${qa.peak_avg_occupancy}). Renforcez les guichets sur ce créneau.`);
  if (hasQueues && qa.quietest_hour != null) recos.push(`Files les plus calmes vers ${qa.quietest_hour}h — fenêtre idéale pour la maintenance ou les pauses.`);
  if (agencies.length) { const w = agencies[0]; recos.push(`Agence où l'on attend le plus : ${w.site} — en moyenne ${fmtDuration(w.wait_avg_s, { compact: true })}, et 9 clients sur 10 en dessous de ${fmtDuration(w.wait_p90_s, { compact: true })}.`); }
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
          subtitle="Tendances de flux · aide à la décision"
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
            ⓘ Fiabilité {d.confidence === "low" ? "limitée" : "partielle"} : seulement {d.active_days} jour(s) de données — les prévisions s&apos;affineront à mesure que l&apos;historique s&apos;accumule.
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
        </div>

        {/* On met en tête ce qui déclenche une décision : l'attente ressentie par
            les clients et la tendance RELATIVE (robustes au sous-comptage). Le total
            absolu de fréquentation est relégué en dernier, cadré par son évolution. */}
        {loading ? <SkeletonKpis count={4} /> : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <Insight label="Attente des clients" icon={Clock}
            value={loading ? "—" : agencies.length ? fmtDuration(agencies[0].wait_avg_s, { compact: true }) : "—"}
            hint={agencies.length ? `${agencies[0].site} · 9 clients sur 10 attendent moins de ${fmtDuration(agencies[0].wait_p90_s, { compact: true })}` : "aucune file"} />
          {hasData && (
            <Insight label="Par rapport à d'habitude" icon={TrendingUp}
              value={loading ? "—" : (today.vs_avg_pct != null ? `${today.vs_avg_pct >= 0 ? "+" : ""}${today.vs_avg_pct}%` : (today.so_far ?? 0))}
              hint={today.projected_eod ? `${today.so_far ?? 0} aujourd'hui · fin de journée estimée ~${today.projected_eod}` : "fréquentation du jour"}
              trend={today.vs_avg_pct} />
          )}
          <Insight label="Heure la plus chargée" icon={CalendarDays}
            value={loading ? "—" : qPeak != null ? `${qPeak}h–${qPeak + 1}h` : "—"}
            hint={qPeak != null ? `en moyenne ${qa.peak_avg_occupancy} pers. en file` : hasQueues ? "pas encore de pic" : "aucune file"} />
          {hasData && (
            <Insight label={`Fréquentation · ${period} j`} icon={TrendingUp}
              value={loading ? "—" : (foot?.total_entries ?? 0)}
              hint={deltaEntries != null ? `${deltaEntries >= 0 ? "+" : ""}${deltaEntries}% vs période précédente` : "entrées comptées"}
              trend={deltaEntries} />
          )}
        </div>)}

        <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>

        {tab === "affluence" && (
          !hasData && !hasQueues ? (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucune donnée. Dessinez une <b>zone « file d&apos;attente »</b> (pour l&apos;affluence des files) ou une <b>ligne de comptage</b> dans « Zones », et activez une caméra.</p></Card>
          ) : (
            <div className="space-y-4">
              {hasData && (
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
              )}

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

                {hasData && (
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
                )}
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
                        <span className="os-num font-semibold text-os-t1">en moyenne {p.avg_occupancy} pers.</span>
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
                        <span className="shrink-0 os-num text-os-t1 font-semibold">{c.entries}<span className="text-os-t4 font-normal"> entrées</span>{c.current_occupancy ? <span className="text-os-t3 font-normal"> · {c.current_occupancy} présents</span> : null}</span>
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
              <div className="flex items-center justify-between mb-1">
                <h3 className="text-[15px] font-semibold text-os-t1">Files & attente</h3>
                {qperf?.wait_threshold_s ? <span className="text-[12px] text-os-t3">objectif : moins de {fmtWait(qperf.wait_threshold_s)}</span> : null}
              </div>
              <p className="text-[12px] text-os-t3 mb-3">« Attente longue » = 9 clients sur 10 attendent moins que cette durée · « Trop longue » = part du temps passé au-dessus de l&apos;objectif.</p>
              {!qperf?.queues?.length ? (
                <p className="text-[13px] text-os-t3 py-8 text-center">Aucune zone de type « file » sur ce périmètre. Créez-en une dans « Zones ».</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px] min-w-[640px]">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-os-t3 border-b border-os-border">
                        <th className="py-2.5 font-semibold">File</th>
                        <th className="py-2.5 font-semibold text-right">Personnes</th>
                        <th className="py-2.5 font-semibold text-right">Attente moyenne</th>
                        <th className="py-2.5 font-semibold text-right">Attente longue</th>
                        <th className="py-2.5 font-semibold text-right">Trop longue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {qperf.queues.map((q) => (
                        <tr key={q.zone_id} className="border-b border-os-border last:border-0">
                          <td className="py-2.5 text-os-t1">{q.name}{q.site ? <span className="text-os-t4"> · {q.site}</span> : null}</td>
                          <td className="py-2.5 os-num text-os-t1 text-right font-semibold">{q.length}</td>
                          <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_avg_s)}</td>
                          <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_p90_s)}</td>
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
                <p className="text-[12px] text-os-t3 mb-4">Attente moyenne par agence · la plus lente en haut</p>
                <div className="space-y-3">
                  {(() => { const max = Math.max(1, ...agencies.map((a) => a.wait_avg_s)); return agencies.map((a) => (
                    <div key={a.site}>
                      <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
                        <span className="truncate text-os-t1">{a.site}</span>
                        <span className="shrink-0 os-num text-os-t1 font-semibold">{fmtWait(a.wait_avg_s)}<span className="text-os-t4 font-normal"> · 9 clients sur 10 sous {fmtWait(a.wait_p90_s)} · {a.over_threshold_pct}% trop longue</span></span>
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

        {tab === "presence" && (
          (absence?.closed_episodes || absence?.current_vacant || staffing?.configured_cameras || staffing?.closed_episodes) ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <Insight label="Postes vacants maintenant" icon={Clock}
                  value={absence?.current_vacant || 0}
                  hint="tolérance dépassée" />
                <Insight label="Épisodes clôturés" icon={Clock}
                  value={absence?.closed_episodes || 0}
                  hint={`sur ${period} j`} />
                <Insight label="Absence cumulée" icon={Clock}
                  value={fmtDuration(absence?.total_absence_s)}
                  hint={`${absence?.affected_posts || 0} poste(s) concerné(s)`} />
                <Insight label="Durée moyenne" icon={Clock}
                  value={fmtDuration(absence?.avg_absence_s)}
                  hint={absence?.max_absence_s ? `maximum ${fmtDuration(absence.max_absence_s)}` : "aucun épisode"} />
              </div>

              <Card className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-[15px] font-semibold text-os-t1">Temps d&apos;absence par jour</h3>
                  <Legend items={[{ label: "Minutes d'absence", color: "var(--os-amber)" }]} />
                </div>
                <TrendChart series={absence?.series || []} keys={[
                  { k: "absence_minutes", label: "Minutes", color: "var(--os-amber)", fill: true },
                ]} />
              </Card>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Postes les plus touchés</h3>
                  <p className="text-[12px] text-os-t3 mb-4">Classement par durée cumulée d&apos;absence</p>
                  {absence?.zones?.length ? (
                    <RankBars rows={absence?.zones || []} valueKey="total_absence_s" labelKey="zone_name" subKey="site"
                      color="var(--os-amber)" fmt={fmtDuration} />
                  ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucun épisode clôturé.</p>}
                </Card>

                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Postes vacants</h3>
                  <p className="text-[12px] text-os-t3 mb-4">Postes ayant déjà dépassé leur tolérance</p>
                  {absence?.current_posts?.length ? (
                    <ul className="space-y-2.5">
                      {(absence?.current_posts || []).map((p) => (
                        <li key={p.episode_id} className="rounded-os border border-os-border p-3 flex items-center justify-between gap-3">
                          <span className="min-w-0">
                            <span className="block text-[13px] font-semibold text-os-t1 truncate">{p.zone_name}</span>
                            <span className="block text-[11px] text-os-t3 truncate">{p.camera_name}{p.site ? ` · ${p.site}` : ""}</span>
                          </span>
                          <span className="os-num text-[12px] font-semibold text-os-red shrink-0">
                            ≥ {fmtDuration(p.vacant_s_at_signal)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucun poste vacant actuellement.</p>}
                </Card>
              </div>

              <div className="pt-2">
                <h3 className="text-[17px] font-semibold text-os-t1">Effectif global par caméra</h3>
              </div>

              <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <Insight label="Caméras configurées" icon={Clock}
                  value={staffing?.configured_cameras || 0}
                  hint="avec minimum et maximum" />
                <Insight label="Sous-effectifs en cours" icon={ShieldAlert}
                  value={staffing?.current_shortages || 0}
                  hint="tolérance dépassée" />
                <Insight label="Durée cumulée" icon={Clock}
                  value={fmtDuration(staffing?.total_shortage_s)}
                  hint={`${staffing?.closed_episodes || 0} épisode(s) clôturé(s)`} />
                <Insight label="Durée moyenne" icon={Clock}
                  value={fmtDuration(staffing?.avg_shortage_s)}
                  hint={staffing?.max_shortage_s ? `maximum ${fmtDuration(staffing.max_shortage_s)}` : "aucun épisode"} />
              </div>

              <Card className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-[15px] font-semibold text-os-t1">Temps de sous-effectif par jour</h3>
                    <p className="text-[12px] text-os-t3">Durée pendant laquelle l&apos;effectif est resté sous le minimum requis</p>
                  </div>
                  <Legend items={[{ label: "Minutes de sous-effectif", color: "var(--os-red)" }]} />
                </div>
                <TrendChart series={staffing?.series || []} keys={[
                  { k: "shortage_minutes", label: "Minutes", color: "var(--os-red)", fill: true },
                ]} />
              </Card>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Caméras les plus touchées</h3>
                  <p className="text-[12px] text-os-t3 mb-4">Classement par durée cumulée de sous-effectif</p>
                  {staffing?.cameras?.length ? (
                    <RankBars rows={staffing.cameras} valueKey="total_shortage_s" labelKey="camera_name" subKey="site"
                      color="var(--os-red)" fmt={fmtDuration} />
                  ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucun sous-effectif clôturé.</p>}
                </Card>

                <Card className="p-5">
                  <h3 className="text-[15px] font-semibold text-os-t1 mb-1">Sous-effectifs en cours</h3>
                  <p className="text-[12px] text-os-t3 mb-4">Dernier effectif constaté au déclenchement</p>
                  {staffing?.current_cameras?.length ? (
                    <ul className="space-y-2.5">
                      {staffing.current_cameras.map((camera) => (
                        <li key={camera.episode_id} className="rounded-os border border-os-border p-3 flex items-center justify-between gap-3">
                          <span className="min-w-0">
                            <span className="block text-[13px] font-semibold text-os-t1 truncate">{camera.camera_name}</span>
                            <span className="block text-[11px] text-os-t3 truncate">{camera.site || "Sans site"} · manque {camera.missing || 0} agent(s)</span>
                          </span>
                          <span className="os-num text-[13px] font-semibold text-os-red shrink-0">
                            {camera.count ?? 0}/{camera.maximum} · min {camera.minimum}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="text-[13px] text-os-t3 py-8 text-center">Aucun sous-effectif actuellement.</p>}
                </Card>
              </div>
            </div>
          ) : (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucune donnée de présence sur la période. Créez des zones « Poste d&apos;agent », puis configurez le minimum et le maximum dans la caméra.</p></Card>
          )
        )}

        {tab === "incidents" && (
          (incidents?.alerts_total || incidents?.crowd_total) ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <Insight label="Alertes" icon={ShieldAlert} value={incidents.alerts_total} hint={`sur ${Math.min(period, 90)} j`} />
                <Insight label="Attroupements" icon={ShieldAlert} value={incidents.crowd_total} hint="attroupements détectés" />
                <Insight label="Critiques" icon={ShieldAlert} value={incidents.by_severity.critical}
                  hint={incidents.by_severity.warning ? `+ ${incidents.by_severity.warning} avertissement(s)` : "aucune"} />
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

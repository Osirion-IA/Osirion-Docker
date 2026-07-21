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
  const [ins, setIns] = useState(null);
  const [foot, setFoot] = useState(null);
  const [queues, setQueues] = useState([]);
  const [occZones, setOccZones] = useState([]);
  const [byCam, setByCam] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const hours = period * 24;
      const [i, f, q, o, bc, inc] = await Promise.all([
        fetchWithRefresh(`/api/analytics/insights?days=${period}`),
        fetchWithRefresh(`/api/analytics/footfall?days=${period}`),
        fetchWithRefresh("/api/analytics/queues"),
        fetchWithRefresh(`/api/analytics/occupancy?hours=${hours}`),
        fetchWithRefresh(`/api/analytics/by-camera?days=${Math.min(period, 90)}`),
        fetchWithRefresh(`/api/analytics/incidents?days=${Math.min(period, 90)}`),
      ]);
      setIns(i?.ok ? await i.json() : null);
      setFoot(f?.ok ? await f.json() : null);
      setQueues(q?.ok ? (await q.json()).queues || [] : []);
      setOccZones(o?.ok ? (await o.json()).zones || [] : []);
      setByCam(bc?.ok ? await bc.json() : null);
      setIncidents(inc?.ok ? await inc.json() : null);
    } finally { setLoading(false); }
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const d = ins || {};
  const today = d.today || {};
  const hasData = (d.total_entries || 0) > 0;
  const peak = d.peak_hour;
  const maxOcc = Math.max(1, ...occZones.map((z) => z.count || 0));

  const recos = [];
  if (hasData) {
    if (peak != null) recos.push(`Affluence maximale vers ${peak}h–${peak + 1}h (${d.peak_hour_count} passages sur ${period} j). Renforcez l'accueil / les guichets sur ce créneau.`);
    if (d.quietest_hour != null) recos.push(`Creux vers ${d.quietest_hour}h — fenêtre idéale pour les tâches de fond, la maintenance ou les pauses.`);
    if (d.busiest_weekday != null) recos.push(`Jour le plus chargé : ${WD_LONG[d.busiest_weekday]} (${d.weekday_avg?.[d.busiest_weekday]} passages/jour en moyenne).`);
    if (byCam?.cameras?.length) { const top = byCam.cameras[0]; recos.push(`Caméra la plus fréquentée : ${top.name}${top.site ? ` (${top.site})` : ""} — ${top.entries} entrées sur la période.`); }
    if (today.vs_avg_pct != null) recos.push(today.vs_avg_pct >= 0
      ? `Aujourd'hui +${today.vs_avg_pct}% vs un ${WD_LONG[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1]} habituel — anticipez une journée chargée.`
      : `Aujourd'hui ${today.vs_avg_pct}% vs d'habitude — affluence plus calme que la normale.`);
  }

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

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <Insight label="Aujourd'hui" icon={TrendingUp}
            value={loading ? "—" : (today.so_far ?? 0)}
            hint={hasData && today.projected_eod ? `projeté ~${today.projected_eod}${today.vs_avg_pct != null ? ` · ${today.vs_avg_pct >= 0 ? "+" : ""}${today.vs_avg_pct}% vs moy.` : ""}` : "passages entrants"}
            trend={today.vs_avg_pct} />
          <Insight label={`Entrées · ${period}j`} icon={TrendingUp}
            value={loading ? "—" : (foot?.total_entries ?? 0)}
            hint={deltaEntries != null ? `${deltaEntries >= 0 ? "+" : ""}${deltaEntries}% vs période préc.` : "période précédente vide"}
            trend={deltaEntries} />
          <Insight label="Heure de pointe" icon={Clock}
            value={loading ? "—" : peak != null ? `${peak}h–${peak + 1}h` : "—"}
            hint={peak != null ? `${d.peak_hour_count} passages` : "pas encore de pic"} />
          <Insight label="Jour le plus chargé" icon={CalendarDays}
            value={loading ? "—" : d.busiest_weekday != null ? WD[d.busiest_weekday] : "—"}
            hint={d.busiest_weekday != null ? `${d.weekday_avg?.[d.busiest_weekday]} passages/j` : "—"} />
        </div>

        <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>

        {tab === "affluence" && (
          !hasData ? (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucune donnée de comptage. Dessinez une ligne de comptage dans « Zones » et activez une caméra — les passages alimenteront ces analyses.</p></Card>
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
                    <h3 className="text-[15px] font-semibold text-os-t1">Passages par heure</h3>
                    <span className="os-num text-[12px] text-os-t3">total {d.total_entries} · {d.active_days} j</span>
                  </div>
                  <HourlyBars hourly={d.hourly || []} peakHour={peak} />
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

              <Card className="p-5">
                <h3 className="text-[15px] font-semibold text-os-t1">Carte de chaleur</h3>
                <p className="text-[12px] text-os-t3 mb-4">Affluence moyenne par jour de semaine et par heure</p>
                <Heatmap matrix={d.heatmap || []} max={d.heatmap_max || 0} />
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
          <Card className="p-5">
            <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Files & attente</h3>
            {queues.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-8 text-center">Aucune zone de type « file ». Créez-en une dans « Zones ».</p>
            ) : (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-os-t3 border-b border-os-border">
                    <th className="py-2.5 font-semibold">File</th><th className="py-2.5 font-semibold text-right">Longueur</th><th className="py-2.5 font-semibold text-right">Attente moy.</th><th className="py-2.5 font-semibold text-right">Attente max</th>
                  </tr>
                </thead>
                <tbody>
                  {queues.map((q) => (
                    <tr key={q.zone_id} className="border-b border-os-border last:border-0">
                      <td className="py-2.5 text-os-t1">{q.name}</td>
                      <td className="py-2.5 os-num text-os-t1 text-right font-semibold">{q.length}</td>
                      <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_avg_s)}</td>
                      <td className="py-2.5 os-num text-os-t2 text-right">{fmtWait(q.wait_max_s)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
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

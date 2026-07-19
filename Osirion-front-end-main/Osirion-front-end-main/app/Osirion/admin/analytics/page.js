"use client";

/**
 * Analytique — tendances de flux ANONYMES exploitables pour la décision
 * (section Analyser, thème clair). Profil horaire + heatmap jour×heure + heure de
 * pointe + projection de fin de journée + prévision des prochaines heures +
 * recommandations. Prévisions = base statistique historique (pas de ML).
 * Données /analytics/insights, /queues, /occupancy.
 */
import { useState, useEffect, useCallback } from "react";
import { TrendingUp, Clock, CalendarDays, Sparkles, ArrowUp, ArrowDown } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const WD = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const WD_LONG = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
const BIZ = Array.from({ length: 17 }, (_, i) => i + 6); // 6h..22h
const hLabel = (h) => `${h}h`;
const fmtWait = (s) => (!s ? "0 s" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
const PERIODS = [{ value: 7, label: "7j" }, { value: 30, label: "30j" }, { value: 90, label: "90j" }];
const TABS = [{ value: "affluence", label: "Affluence" }, { value: "queues", label: "Files & attente" }, { value: "occupancy", label: "Occupation" }];

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

// Graphe à barres horaires (total sur la fenêtre), pic mis en évidence.
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

// Heatmap jour de semaine × heure (moyenne d'entrées), échelle bleue.
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
  const [queues, setQueues] = useState([]);
  const [occZones, setOccZones] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const hours = period * 24;
      const [i, q, o] = await Promise.all([
        fetchWithRefresh(`/api/analytics/insights?days=${period}`),
        fetchWithRefresh("/api/analytics/queues"),
        fetchWithRefresh(`/api/analytics/occupancy?hours=${hours}`),
      ]);
      setIns(i?.ok ? await i.json() : null);
      setQueues(q?.ok ? (await q.json()).queues || [] : []);
      setOccZones(o?.ok ? (await o.json()).zones || [] : []);
    } finally { setLoading(false); }
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const d = ins || {};
  const today = d.today || {};
  const hasData = (d.total_entries || 0) > 0;
  const peak = d.peak_hour;
  const maxOcc = Math.max(1, ...occZones.map((z) => z.count || 0));

  // Recommandations dérivées (langage décision).
  const recos = [];
  if (hasData) {
    if (peak != null) recos.push(`Affluence maximale vers ${peak}h–${peak + 1}h (${d.peak_hour_count} passages sur ${period} j). Renforcez l'accueil / les guichets sur ce créneau.`);
    if (d.quietest_hour != null) recos.push(`Creux vers ${d.quietest_hour}h — fenêtre idéale pour les tâches de fond, la maintenance ou les pauses.`);
    if (d.busiest_weekday != null) recos.push(`Jour le plus chargé : ${WD_LONG[d.busiest_weekday]} (${d.weekday_avg?.[d.busiest_weekday]} passages/jour en moyenne).`);
    if (today.vs_avg_pct != null) recos.push(today.vs_avg_pct >= 0
      ? `Aujourd'hui +${today.vs_avg_pct}% vs un ${WD_LONG[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1]} habituel — anticipez une journée chargée.`
      : `Aujourd'hui ${today.vs_avg_pct}% vs d'habitude — affluence plus calme que la normale.`);
  }

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Analytique"
          subtitle="Tendances de flux anonymes · aide à la décision"
          actions={<Segmented value={period} onChange={setPeriod} options={PERIODS} size="sm" />}
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
          <Insight label="Heure de pointe" icon={Clock}
            value={loading ? "—" : peak != null ? `${peak}h–${peak + 1}h` : "—"}
            hint={peak != null ? `${d.peak_hour_count} passages` : "pas encore de pic"} />
          <Insight label="Jour le plus chargé" icon={CalendarDays}
            value={loading ? "—" : d.busiest_weekday != null ? WD[d.busiest_weekday] : "—"}
            hint={d.busiest_weekday != null ? `${d.weekday_avg?.[d.busiest_weekday]} passages/j` : "—"} />
          <Insight label="Prévision prochaine heure" icon={Sparkles}
            value={loading ? "—" : d.forecast?.length ? `~${d.forecast[0].expected}` : "—"}
            hint={d.forecast?.length ? `attendus à ${d.forecast[0].hour}h` : "hors plage"} />
        </div>

        <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>

        {tab === "affluence" && (
          !hasData ? (
            <Card className="p-5"><p className="text-[13px] text-os-t3 py-12 text-center">Aucune donnée de comptage. Dessinez une ligne de comptage dans « Zones » et activez une caméra — les passages alimenteront ces analyses.</p></Card>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-4">
                <Card className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[15px] font-semibold text-os-t1">Passages par heure</h3>
                    <span className="os-num text-[12px] text-os-t3">total {d.total_entries} · {d.active_days} j</span>
                  </div>
                  <HourlyBars hourly={d.hourly || []} peakHour={peak} />
                </Card>

                <div className="space-y-4">
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
      </div>
    </OsShell>
  );
}

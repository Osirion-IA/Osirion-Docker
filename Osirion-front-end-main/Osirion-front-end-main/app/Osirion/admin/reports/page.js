"use client";

/**
 * Rapports — SYNTHÈSE d'activité (section Analyser, thème clair). Résumé décisionnel
 * (affluence, files & attente, incidents, disponibilité caméras) sur une période /
 * agence, exportable en PDF. Le journal d'événements brut + son export sont sur la
 * page « Événements ». Aucune donnée personnelle.
 */
import { useState, useMemo, useEffect, useCallback } from "react";
import { FileText, BarChart3 } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Segmented, EmptyState } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const PERIODS = [{ value: 7, label: "7j" }, { value: 30, label: "30j" }, { value: 90, label: "90j" }];
const fmtWait = (s) => (!s ? "0 s" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);

// PDF de synthèse (résumé décisionnel).
function printSynthesis(sections, meta) {
  const w = window.open("", "_blank");
  if (!w) { alert("Autorisez les pop-ups pour générer le PDF."); return; }
  const escH = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const secHtml = sections.map((sec) => `
    <section><h2>${escH(sec.title)}</h2><table class="kv">${sec.rows.map((r) => `<tr><td class="k">${escH(r[0])}</td><td class="v">${escH(r[1])}</td></tr>`).join("")}</table></section>`).join("");
  w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Synthèse d'activité — Qwiper Sentinel</title><style>
    body{font-family:Arial,sans-serif;color:#111;margin:28px;} header{display:flex;justify-content:space-between;border-bottom:2px solid #1c2126;padding-bottom:12px;margin-bottom:18px;}
    h1{font-size:22px;margin:0 0 4px;} .meta{font-size:12px;color:#555;} .brand{font-size:14px;font-weight:bold;letter-spacing:2px;color:#1c2126;}
    section{margin:0 0 18px;break-inside:avoid;} h2{font-size:14px;margin:0 0 8px;padding-bottom:4px;border-bottom:1px solid #e5e7eb;color:#1c2126;}
    table.kv{width:100%;border-collapse:collapse;font-size:13px;} .kv td{padding:5px 6px;border-bottom:1px solid #f0f2f4;} .kv .k{color:#555;width:55%;} .kv .v{font-weight:bold;text-align:right;}
    @media print{body{margin:14mm;} @page{size:A4 portrait;}}
    </style></head><body><header><div><h1>Synthèse d'activité</h1><div class="meta">Période : ${escH(meta.period)} · Périmètre : ${escH(meta.scope)}</div><div class="meta">Généré le ${escH(meta.generatedAt)}</div></div><div class="brand">QWIPER SENTINEL</div></header>${secHtml}</body></html>`);
  w.document.close();
  setTimeout(() => { try { w.focus(); w.print(); } catch { /* */ } }, 300);
}

export default function ReportsPage() {
  const [period, setPeriod] = useState(30);
  const [groupId, setGroupId] = useState("");
  const [camId, setCamId] = useState("");
  const [groups, setGroups] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [syn, setSyn] = useState(null);
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
    const f = camId ? `camera_id=${camId}` : groupId ? `group_id=${groupId}` : "";
    const fq = f ? `&${f}` : "";
    const days = Math.min(period, 90);
    try {
      const [foot, qa, qp, inc, cs] = await Promise.all([
        fetchWithRefresh(`/api/analytics/footfall?days=${days}${camId ? `&camera_id=${camId}` : ""}`).then((r) => (r?.ok ? r.json() : null)),
        fetchWithRefresh(`/api/analytics/queue-affluence?days=${days}${fq}`).then((r) => (r?.ok ? r.json() : null)),
        fetchWithRefresh(`/api/analytics/queue-performance?days=${days}${fq}`).then((r) => (r?.ok ? r.json() : null)),
        fetchWithRefresh(`/api/analytics/incidents?days=${days}`).then((r) => (r?.ok ? r.json() : null)),
        fetchWithRefresh(`/api/camera-status/stats?days=${days}${fq}`).then((r) => (r?.ok ? r.json() : null)),
      ]);
      setSyn({ foot, qa, qp, inc, cs });
    } finally { setLoading(false); }
  }, [period, groupId, camId]);
  useEffect(() => { load(); }, [load]);

  const scopeLabel = camId ? (cameras.find((c) => String(c.id) === String(camId))?.cam_name || `Caméra ${camId}`)
    : groupId ? (groups.find((g) => String(g.id) === String(groupId))?.name || "Agence") : "Tous les sites";

  const sections = useMemo(() => {
    if (!syn) return [];
    const { foot, qa, qp, inc, cs } = syn;
    const topQ = qp?.queues?.[0];
    const topA = qp?.agencies?.[0];
    return [
      { title: "Affluence", rows: [
        ["Entrées (période)", foot?.total_entries ?? 0],
        ["Sorties (période)", foot?.total_exits ?? 0],
        ["Évolution vs période précédente", foot?.delta_entries_pct != null ? `${foot.delta_entries_pct >= 0 ? "+" : ""}${foot.delta_entries_pct}%` : "—"],
        ["Pic des files (occupation)", qa?.peak_hour != null ? `${qa.peak_hour}h–${qa.peak_hour + 1}h (moy. ${qa.peak_avg_occupancy})` : "—"],
      ] },
      { title: "Files & attente", rows: [
        ["Files suivies", qp?.queues?.length ?? 0],
        ["File la plus lente", topQ ? `${topQ.name}${topQ.site ? ` (${topQ.site})` : ""}` : "—"],
        ["Attente moyenne (max file)", topQ ? fmtWait(topQ.wait_avg_s) : "—"],
        ["Attente P90 (max file)", topQ ? fmtWait(topQ.wait_p90_s) : "—"],
        ["Agence la plus lente", topA ? `${topA.site} — moy. ${fmtWait(topA.wait_avg_s)}, P90 ${fmtWait(topA.wait_p90_s)}` : "—"],
      ] },
      { title: "Incidents (global)", rows: [
        ["Alertes", inc?.alerts_total ?? 0],
        ["Attroupements détectés", inc?.crowd_total ?? 0],
        ["Critiques", inc?.by_severity?.critical ?? 0],
        ["Taux de résolution", inc?.resolution_rate != null ? `${inc.resolution_rate}%` : "—"],
      ] },
      { title: "Disponibilité caméras", rows: [
        ["Disponibilité moyenne", cs?.summary?.avg_uptime_pct != null ? `${cs.summary.avg_uptime_pct}%` : "—"],
        ["Déconnexions", cs?.summary?.total_disconnections ?? 0],
        ["Temps hors-ligne cumulé", fmtWait(cs?.summary?.total_offline_seconds || 0)],
        ["Hors ligne actuellement", cs?.summary?.currently_offline ?? 0],
      ] },
    ];
  }, [syn]);

  const doPrint = () => printSynthesis(sections, {
    period: `${period} derniers jours`, scope: scopeLabel, generatedAt: new Date().toLocaleString("fr-FR"),
  });

  const sel = "rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none focus:border-os-t3";
  const camOptions = cameras.filter((c) => !groupId || (c.group_ids || []).includes(Number(groupId)));

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Rapports"
          subtitle="Synthèse d'activité · aide à la décision (le journal brut est sur « Événements »)"
          actions={
            <button onClick={doPrint} disabled={loading || !syn} className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-40 inline-flex items-center gap-2">
              <FileText className="h-4 w-4" /> Exporter (PDF)
            </button>
          }
        />

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Segmented value={period} onChange={setPeriod} options={PERIODS} size="sm" />
          <select value={groupId} onChange={(e) => { setGroupId(e.target.value); setCamId(""); }} className={sel}>
            <option value="">Toutes les agences</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <select value={camId} onChange={(e) => setCamId(e.target.value)} className={sel}>
            <option value="">Toutes les caméras</option>
            {camOptions.map((c) => <option key={c.id} value={c.id}>{c.cam_name || `Caméra ${c.id}`}</option>)}
          </select>
        </div>

        <Card className="p-4 mb-4">
          <div className="flex items-center gap-3">
            <span className="h-10 w-10 grid place-items-center rounded-os bg-os-cta text-white"><BarChart3 className="h-5 w-5" /></span>
            <div>
              <h3 className="text-[15px] font-semibold text-os-t1">Synthèse d&apos;activité</h3>
              <p className="text-[12px] text-os-t3">{period} derniers jours · {scopeLabel}</p>
            </div>
          </div>
        </Card>

        {loading ? (
          <EmptyState icon={BarChart3}>Calcul de la synthèse…</EmptyState>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sections.map((sec) => (
              <Card key={sec.title} className="p-5">
                <h3 className="text-[15px] font-semibold text-os-t1 mb-3">{sec.title}</h3>
                <table className="w-full text-[13px]">
                  <tbody>
                    {sec.rows.map((r, i) => (
                      <tr key={i} className="border-b border-os-border last:border-0">
                        <td className="py-2 text-os-t3">{r[0]}</td>
                        <td className="py-2 os-num text-right font-semibold text-os-t1">{r[1]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            ))}
          </div>
        )}
      </div>
    </OsShell>
  );
}

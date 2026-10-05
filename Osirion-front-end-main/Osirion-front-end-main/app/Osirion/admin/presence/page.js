"use client";

/**
 * Présence des agents — vue métier d'aide à la décision.
 *
 * Le périmètre est strict : seules les caméras possédant au moins une zone
 * active `presence` apparaissent. La configuration reste dans Caméras/Zones.
 */
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Camera, CheckCircle2, Clock3,
  Globe2, Image as ImageIcon, UserMinus, UserRoundCheck, UsersRound,
} from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { Card, EmptyState, RefreshButton, Segmented } from "../_osirion/ui";
import CameraStream from "../live/CameraStream";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { CORE_URL } from "../../../lib/publicUrls";
import { parseUtc, dateTime, elapsed } from "../../../lib/format";

const PERIODS = [
  { value: 7, label: "7 jours" },
  { value: 30, label: "30 jours" },
  { value: 90, label: "90 jours" },
];
const EVENT_META = {
  POST_VACANT: { label: "Poste vacant", color: "var(--os-red)" },
  POST_ABSENCE: { label: "Absence clôturée", color: "var(--os-amber)" },
  STAFFING_LOW: { label: "Sous-effectif", color: "var(--os-red)" },
  STAFFING_RECOVERED: { label: "Effectif rétabli", color: "var(--os-green)" },
};
const STATUS_META = {
  ok: { label: "Occupé / normal", color: "var(--os-green)" },
  low: { label: "Sous-effectif", color: "var(--os-red)" },
  staffing_pending: { label: "Effectif en observation", color: "var(--os-amber)" },
  vacant: { label: "Poste vacant", color: "var(--os-amber)" },
  confirming: { label: "Présence à confirmer", color: "var(--os-blue)" },
  vacancy_pending: { label: "Vacance en observation", color: "var(--os-amber)" },
  off_schedule: { label: "Hors horaire", color: "var(--os-blue)" },
  unavailable: { label: "Caméra indisponible", color: "var(--os-t3)" },
  unconfigured: { label: "Horaire non configuré", color: "var(--os-t3)" },
  pending: { label: "En attente", color: "var(--os-t3)" },
};

function aggregatePresenceState(zones) {
  const priority = ["unavailable", "vacant", "confirming", "vacancy_pending", "occupied", "off_schedule", "unconfigured", "initializing"];
  return priority.find((state) => zones.some((zone) => zone.state === state)) || "initializing";
}

function duration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}
function formatMinutes(minutes) {
  const value = Math.max(0, Math.round(Number(minutes) || 0));
  if (value < 60) return `${value} min`;
  const hours = Math.floor(value / 60);
  return `${hours} h ${String(value % 60).padStart(2, "0")}`;
}
function snapshotUrl(value) {
  if (!value) return null;
  return String(value).startsWith("http") ? value : `/api/images?path=${encodeURIComponent(value)}`;
}
function attachClosureSnapshots(events) {
  const openingByEpisode = new Map();
  for (const event of events) {
    const episodeId = event.meta?.episode_id;
    if (event.event_type === "POST_VACANT" && episodeId && event.snapshot_url) {
      openingByEpisode.set(String(episodeId), event.snapshot_url);
    }
  }
  return events.map((event) => {
    if (event.event_type !== "POST_ABSENCE" || event.snapshot_url) return event;
    const openingSnapshot = openingByEpisode.get(String(event.meta?.episode_id || ""));
    return openingSnapshot ? {
      ...event,
      snapshot_url: openingSnapshot,
      snapshot_fallback: "vacancy_event",
    } : event;
  });
}
function eventValue(event) {
  const meta = event?.meta || {};
  if (event?.event_type === "STAFFING_LOW") return `${meta.count ?? 0}/${meta.maximum ?? "—"} agents · ${meta.missing ?? "—"} manquant(s)`;
  if (event?.event_type === "STAFFING_RECOVERED") return `rétabli à ${meta.count ?? "—"} agent(s) · épisode ${duration(meta.shortage_s)}`;
  if (event?.event_type === "POST_ABSENCE") return `${meta.zone_name || "Poste"} · absence ${duration(meta.absence_s)}`;
  return `${meta.zone_name || "Poste"} · vacant depuis ${duration(meta.vacant_s)}`;
}

function Kpi({ icon: Icon, label, value, hint, tone = "neutral" }) {
  const toneClass = {
    neutral: "text-os-t2 bg-os-card-2", good: "text-os-green bg-os-green/10",
    warn: "text-os-amber bg-os-amber/10", bad: "text-os-red bg-os-red/10",
  }[tone];
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-os-t3">{label}</p>
          <p className="os-num mt-2 text-[25px] leading-none font-bold text-os-t1">{value}</p>
          <p className="mt-2 text-[11px] text-os-t3">{hint}</p>
        </div>
        <span className={`h-10 w-10 shrink-0 rounded-os grid place-items-center ${toneClass}`}><Icon className="h-5 w-5" /></span>
      </div>
    </Card>
  );
}

function PeriodStat({ label, value, hint }) {
  return (
    <div className="py-3 border-b border-os-border last:border-0">
      <div className="flex items-end justify-between gap-3">
        <span className="text-[11px] text-os-t3">{label}</span>
        <span className="os-num text-[15px] font-semibold text-os-t1">{value}</span>
      </div>
      {hint && <p className="mt-0.5 text-[9px] text-os-t4 text-right">{hint}</p>}
    </div>
  );
}

function mergeSeries(absence, staffing) {
  const byDate = new Map();
  for (const row of absence?.series || []) byDate.set(row.date, {
    date: row.date, absenceMinutes: Number(row.absence_minutes) || 0,
    absenceEpisodes: Number(row.episodes) || 0, shortageMinutes: 0, shortageEpisodes: 0,
  });
  for (const row of staffing?.series || []) {
    const current = byDate.get(row.date) || { date: row.date, absenceMinutes: 0, absenceEpisodes: 0, shortageMinutes: 0, shortageEpisodes: 0 };
    current.shortageMinutes = Number(row.shortage_minutes) || 0;
    current.shortageEpisodes = Number(row.episodes) || 0;
    byDate.set(row.date, current);
  }
  return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function DurationTrend({ absence, staffing }) {
  const rows = useMemo(() => mergeSeries(absence, staffing), [absence, staffing]);
  const hasData = rows.some((row) => row.absenceMinutes || row.shortageMinutes);
  if (!rows.length || !hasData) return <EmptyState icon={Activity}>Aucune durée d&apos;incident sur la période.</EmptyState>;

  const W = 820, H = 270, left = 78, right = 22, top = 22, bottom = 43;
  const plotW = W - left - right, plotH = H - top - bottom;
  const maxValue = Math.max(1, ...rows.flatMap((row) => [row.absenceMinutes, row.shortageMinutes]));
  const x = (index) => left + (rows.length === 1 ? plotW / 2 : (index / (rows.length - 1)) * plotW);
  const y = (value) => top + plotH - (value / maxValue) * plotH;
  const path = (key) => rows.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(row[key]).toFixed(1)}`).join(" ");
  const yTicks = [0, .25, .5, .75, 1].map((ratio) => ({ ratio, value: Math.round(maxValue * ratio) }));
  const xIndexes = Array.from(new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1]));

  return (
    <div className="p-4">
      <div className="flex flex-wrap items-center gap-4 mb-2 text-[10px] text-os-t3">
        <span className="inline-flex items-center gap-1.5"><i className="w-5 h-0.5 bg-os-amber" /> Absence aux postes</span>
        <span className="inline-flex items-center gap-1.5"><i className="w-5 h-0.5 bg-os-red" /> Sous-effectif</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Évolution quotidienne des minutes d'absence et de sous-effectif">
        <title>Durée quotidienne des incidents de présence</title>
        {yTicks.map((tick) => (
          <g key={tick.ratio}>
            <line x1={left} x2={W - right} y1={y(maxValue * tick.ratio)} y2={y(maxValue * tick.ratio)} stroke="var(--os-border)" strokeWidth="1" />
            <text x={left - 9} y={y(maxValue * tick.ratio) + 4} textAnchor="end" fill="var(--os-t4)" fontSize="10">{formatMinutes(tick.value)}</text>
          </g>
        ))}
        <line x1={left} x2={left} y1={top} y2={top + plotH} stroke="var(--os-border-2)" />
        <line x1={left} x2={W - right} y1={top + plotH} y2={top + plotH} stroke="var(--os-border-2)" />
        <path d={path("absenceMinutes")} fill="none" stroke="var(--os-amber)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        <path d={path("shortageMinutes")} fill="none" stroke="var(--os-red)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        {rows.length <= 31 && rows.map((row, index) => (
          <g key={row.date}>
            <circle cx={x(index)} cy={y(row.absenceMinutes)} r="3" fill="var(--os-amber)"><title>{row.date} · {formatMinutes(row.absenceMinutes)} d&apos;absence</title></circle>
            <circle cx={x(index)} cy={y(row.shortageMinutes)} r="3" fill="var(--os-red)"><title>{row.date} · {formatMinutes(row.shortageMinutes)} de sous-effectif</title></circle>
          </g>
        ))}
        {xIndexes.map((index) => <text key={index} x={x(index)} y={H - 17} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"} fill="var(--os-t4)" fontSize="10">{new Date(`${rows[index].date}T12:00:00`).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" })}</text>)}
        <text x="14" y={top + plotH / 2} transform={`rotate(-90 14 ${top + plotH / 2})`} textAnchor="middle" fill="var(--os-t3)" fontSize="10">Durée</text>
      </svg>
    </div>
  );
}

function IncidentBars({ absence, staffing }) {
  const rows = useMemo(() => mergeSeries(absence, staffing).slice(-14), [absence, staffing]);
  const max = Math.max(1, ...rows.map((row) => row.absenceEpisodes + row.shortageEpisodes));
  if (!rows.length) return <EmptyState icon={Clock3}>Aucune donnée quotidienne.</EmptyState>;
  return (
    <div className="h-60 px-4 pt-5 pb-3 flex items-end gap-2">
      {rows.map((row) => {
        const total = row.absenceEpisodes + row.shortageEpisodes;
        const height = Math.max(total ? 8 : 2, Math.round((total / max) * 160));
        const absenceHeight = total ? Math.round((row.absenceEpisodes / total) * height) : 0;
        return (
          <div key={row.date} className="min-w-0 flex-1 h-full flex flex-col justify-end items-center group" title={`${row.date} · ${row.absenceEpisodes} absence(s) · ${row.shortageEpisodes} sous-effectif(s)`}>
            <span className="os-num mb-1 text-[10px] text-os-t3 opacity-0 group-hover:opacity-100">{total}</span>
            <div className="w-full max-w-8 rounded-t-sm overflow-hidden bg-os-card-2" style={{ height }}>
              <div className="w-full bg-os-amber" style={{ height: absenceHeight }} />
              <div className="w-full bg-os-red" style={{ height: Math.max(0, height - absenceHeight) }} />
            </div>
            <span className="mt-2 os-num text-[9px] text-os-t4 truncate w-full text-center">{new Date(`${row.date}T12:00:00`).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })}</span>
          </div>
        );
      })}
    </div>
  );
}

function StatusDistribution({ rows }) {
  const order = ["ok", "confirming", "vacancy_pending", "staffing_pending", "vacant", "low", "off_schedule", "unavailable", "unconfigured", "pending"];
  const values = order.map((status) => ({ status, count: rows.filter((row) => row.status === status).length })).filter((item) => item.count);
  const total = Math.max(1, rows.length);
  return (
    <Card className="p-4 mb-4">
      <div className="flex flex-col lg:flex-row lg:items-center gap-4">
        <div className="lg:w-52 shrink-0">
          <h2 className="text-[13px] font-semibold text-os-t1">Situation actuelle</h2>
          <p className="text-[10px] text-os-t3">Uniquement les caméras avec poste agent</p>
        </div>
        <div className="flex-1">
          <div className="h-3 flex overflow-hidden rounded-full bg-os-card-2">
            {values.map((item) => <span key={item.status} style={{ width: `${(item.count / total) * 100}%`, background: STATUS_META[item.status].color }} />)}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
            {values.map((item) => (
              <span key={item.status} className="inline-flex items-center gap-1.5 text-[10px] text-os-t3">
                <i className="h-2 w-2 rounded-full" style={{ background: STATUS_META[item.status].color }} />
                {STATUS_META[item.status].label} <b className="os-num text-os-t2">{item.count}</b>
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

function stateHint(zone) {
  if (zone.state === "occupied") return `${zone.confirmed_count || 1} présence(s) confirmée(s)`;
  if (zone.state === "confirming") return `${zone.candidate_count || 1} candidat(s) · confirmation en cours`;
  if (zone.state === "vacancy_pending") return `Alerte dans ${duration(zone.alert_in_s)}`;
  if (zone.state === "vacant") return `Vacant depuis ${duration(zone.vacant_for_s)}`;
  if (zone.state === "off_schedule") return "Surveillance suspendue par le régime horaire";
  if (zone.state === "unavailable") return `Décision suspendue · ${zone.monitoring_reason || "flux absent"}`;
  if (zone.state === "unconfigured") return "Aucun régime horaire valide";
  return "Initialisation de la surveillance";
}

function LivePostStates({ rows }) {
  return (
    <Card className="overflow-hidden mb-4">
      <div className="px-5 py-4 border-b border-os-border flex items-center justify-between gap-3">
        <h2 className="text-[14px] font-semibold text-os-t1">État instantané des postes</h2>
        <span className="os-num text-[10px] text-os-t4">{rows.length} caméra(s)</span>
      </div>
      <div className="divide-y divide-os-border max-h-96 overflow-y-auto">
        {rows.map((row) => {
          const meta = STATUS_META[row.status] || STATUS_META.pending;
          const liveZones = row.live?.presence_zones || [];
          return (
            <div key={row.camera.id} className="px-5 py-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-os-t1 truncate">{row.camera.cam_name}</p>
                  <p className="text-[10px] text-os-t4 truncate">{row.camera.location || "Emplacement non renseigné"}</p>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold" style={{ color: meta.color, background: `color-mix(in srgb, ${meta.color} 10%, transparent)` }}>
                  <i className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />{meta.label}
                </span>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {liveZones.length ? liveZones.map((zone) => {
                  const zoneStatus = zone.state === "occupied" ? "ok" : zone.state;
                  const zoneMeta = STATUS_META[zoneStatus] || STATUS_META.pending;
                  return (
                    <div key={zone.zone_id} className="rounded-os border border-os-border bg-os-card-2 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-semibold text-os-t2 truncate">{zone.zone_name || `Poste ${zone.zone_id}`}</span>
                        <i className="h-2 w-2 rounded-full shrink-0" style={{ background: zoneMeta.color }} />
                      </div>
                      <p className="mt-1 text-[10px] text-os-t4">{stateHint(zone)}</p>
                    </div>
                  );
                }) : (
                  <div className="rounded-os border border-os-border bg-os-card-2 px-3 py-2 text-[10px] text-os-t4 sm:col-span-2">
                    {row.live ? "Configuration de poste en cours de chargement" : "Aucune donnée temps réel reçue"}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function CalibrationPanel({ rows, cameraId, onCameraChange }) {
  const row = rows.find((item) => String(item.camera.id) === String(cameraId)) || rows[0];
  if (!row) return null;
  const liveZones = row.live?.presence_zones || [];
  const cameraStatus = row.live?.monitoring_available ? "Flux exploitable" : "Décision suspendue";
  return (
    <Card className="overflow-hidden mb-4">
      <div className="px-5 py-4 border-b border-os-border flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div>
          <h2 className="text-[14px] font-semibold text-os-t1">Calibration et contrôle terrain</h2>
          <p className="text-[11px] text-os-t3">Vérifiez sur le flux réel le périmètre, la détection et le délai avant toute alerte</p>
        </div>
        <select value={row.camera.id} onChange={(event) => onCameraChange(event.target.value)} className="h-9 min-w-56 rounded-os border border-os-border bg-os-card px-3 text-[12px] text-os-t1 outline-none focus:border-os-t3">
          {rows.map((item) => <option key={item.camera.id} value={item.camera.id}>{item.camera.cam_name}</option>)}
        </select>
      </div>
      <div className="grid xl:grid-cols-[1.45fr_0.55fr]">
        <div className="relative aspect-video bg-[#0d0f12] border-b xl:border-b-0 xl:border-r border-os-border">
          <CameraStream cameraId={row.camera.id} showStats />
          <span className={`absolute left-3 bottom-3 z-20 rounded-os px-2.5 py-1 text-[10px] font-semibold backdrop-blur-sm ${row.live?.monitoring_available ? "bg-os-green/90 text-white" : "bg-black/70 text-white/70"}`}>{cameraStatus}</span>
        </div>
        <div className="divide-y divide-os-border max-h-[420px] overflow-y-auto">
          {liveZones.map((zone) => {
            const status = zone.state === "occupied" ? "ok" : zone.state;
            const meta = STATUS_META[status] || STATUS_META.pending;
            return (
              <div key={zone.zone_id} className="p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] font-semibold text-os-t1 truncate">{zone.zone_name}</p>
                  <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: meta.color }} />
                </div>
                <p className="mt-1 text-[10px] font-semibold" style={{ color: meta.color }}>{meta.label}</p>
                <p className="mt-1 text-[10px] text-os-t4">{stateHint(zone)}</p>
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
                  <div><dt className="text-os-t4">Confirmées</dt><dd className="os-num font-semibold text-os-t2">{zone.confirmed_count ?? 0}</dd></div>
                  <div><dt className="text-os-t4">Candidates</dt><dd className="os-num font-semibold text-os-t2">{zone.candidate_count ?? 0}</dd></div>
                  <div><dt className="text-os-t4">Confirmation</dt><dd className="os-num font-semibold text-os-t2">{duration(zone.min_presence_s)}</dd></div>
                  <div><dt className="text-os-t4">Tolérance absence</dt><dd className="os-num font-semibold text-os-t2">{zone.absence_tolerance_s == null ? "—" : duration(zone.absence_tolerance_s)}</dd></div>
                  <div><dt className="text-os-t4">Détections image</dt><dd className="os-num font-semibold text-os-t2">{zone.frame_person_detections ?? 0}</dd></div>
                  <div><dt className="text-os-t4">Confiance max.</dt><dd className="os-num font-semibold text-os-t2">{zone.frame_max_confidence ? `${Math.round(zone.frame_max_confidence * 100)} %` : "—"}</dd></div>
                  <div><dt className="text-os-t4">Inférence</dt><dd className="os-num font-semibold text-os-t2">{zone.inference_imgsz ? `${zone.inference_imgsz}px` : "—"}</dd></div>
                  <div><dt className="text-os-t4">Recouvrement min.</dt><dd className="os-num font-semibold text-os-t2">{zone.bbox_overlap_threshold != null ? `${Math.round(zone.bbox_overlap_threshold * 100)} %` : "—"}</dd></div>
                </dl>
              </div>
            );
          })}
          {!liveZones.length && <div className="p-5 text-[11px] text-os-t3">Les paramètres de calibration apparaîtront dès la première décision du moteur.</div>}
          <div className="p-4 bg-os-card-2">
            <p className="text-[10px] text-os-t3 leading-relaxed">Le contour doit couvrir le corps ou les pieds de l&apos;agent sans englober la zone de passage. Une boîte cyan est une détection anonyme ; le contour vert signifie une présence confirmée.</p>
            <Link href="/Osirion/admin/zones" className="inline-flex mt-3 text-[11px] font-semibold text-os-blue hover:underline">Ajuster le tracé ou le régime horaire</Link>
          </div>
        </div>
      </div>
    </Card>
  );
}

function GroupAnalytics({ absence, staffing, schedules }) {
  const absenceMap = new Map((absence?.schedules || []).map((row) => [Number(row.work_schedule_id), row]));
  const staffingMap = new Map((staffing?.schedules || []).map((row) => [Number(row.work_schedule_id), row]));
  const ids = new Set([
    ...schedules.map((row) => Number(row.id)),
    ...absenceMap.keys(),
    ...staffingMap.keys(),
  ]);
  const rows = [...ids].map((id) => {
    const schedule = schedules.find((item) => Number(item.id) === id);
    const abs = absenceMap.get(id) || {};
    const staff = staffingMap.get(id) || {};
    return {
      id,
      name: schedule?.name || abs.work_schedule_name || staff.work_schedule_name || `Groupe ${id}`,
      posts: schedule?.zones_count ?? "—",
      absence: abs.total_absence_s || 0,
      shortage: staff.total_shortage_s || 0,
      incidents: (abs.episodes || 0) + (staff.episodes || 0),
      open: (abs.current_vacant || 0) + (staff.current_shortages || 0),
    };
  }).sort((a, b) => (b.absence + b.shortage) - (a.absence + a.shortage));
  return (
    <Card className="overflow-hidden mt-4">
      <div className="px-5 py-4 border-b border-os-border flex items-center gap-3">
        <span className="h-9 w-9 rounded-os bg-os-card-2 grid place-items-center text-os-t2"><Globe2 className="h-4 w-4" /></span>
        <h2 className="text-[14px] font-semibold text-os-t1">Comparaison par groupe / pays</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left min-w-[640px]">
          <thead><tr className="border-b border-os-border text-[10px] uppercase tracking-wide text-os-t4"><th className="px-5 py-2.5 font-semibold">Groupe</th><th className="px-3 py-2.5 font-semibold">Postes</th><th className="px-3 py-2.5 font-semibold">Absence</th><th className="px-3 py-2.5 font-semibold">Sous-effectif</th><th className="px-3 py-2.5 font-semibold">Épisodes</th><th className="px-5 py-2.5 font-semibold">Ouverts</th></tr></thead>
          <tbody className="divide-y divide-os-border">
            {rows.map((row) => <tr key={row.id} className="text-[11px]"><td className="px-5 py-3 font-semibold text-os-t1">{row.name}</td><td className="px-3 py-3 os-num text-os-t3">{row.posts}</td><td className="px-3 py-3 os-num text-os-t2">{duration(row.absence)}</td><td className="px-3 py-3 os-num text-os-t2">{duration(row.shortage)}</td><td className="px-3 py-3 os-num text-os-t3">{row.incidents}</td><td className={`px-5 py-3 os-num font-semibold ${row.open ? "text-os-red" : "text-os-green"}`}>{row.open}</td></tr>)}
            {!rows.length && <tr><td colSpan="6" className="px-5 py-8 text-center text-[12px] text-os-t3">Aucun groupe horaire configuré.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function EvidenceDetails({ event }) {
  const eventMeta = event?.meta || {};
  const decision = eventMeta.decision || {};
  const fields = [
    ["Présences confirmées", decision.confirmed_count],
    ["Candidats observés", decision.candidate_count],
    ["Détections sur l’image", decision.frame_person_detections],
    ["Confiance maximale", decision.frame_max_confidence != null ? `${Math.round(Number(decision.frame_max_confidence) * 100)} %` : null],
    ["Taille d’inférence", decision.inference_imgsz ? `${decision.inference_imgsz}px` : null],
    ["Recouvrement requis", decision.bbox_overlap_threshold != null ? `${Math.round(Number(decision.bbox_overlap_threshold) * 100)} %` : null],
  ].filter(([, value]) => value !== undefined && value !== null);
  if (!fields.length) return null;
  return (
    <dl className="mt-3 pt-3 border-t border-os-border grid grid-cols-2 gap-x-3 gap-y-2">
      {fields.map(([label, value]) => <div key={label}><dt className="text-[9px] text-os-t4">{label}</dt><dd className="os-num text-[11px] font-semibold text-os-t2">{value}</dd></div>)}
    </dl>
  );
}

function EventEvidence({ event }) {
  if (!event) return <Card><EmptyState icon={ImageIcon}>Aucun événement sur la période.</EmptyState></Card>;
  const image = snapshotUrl(event.snapshot_url);
  const meta = EVENT_META[event.event_type] || { label: event.event_type, color: "var(--os-t3)" };
  return (
    <Card className="overflow-hidden h-fit">
      <div className="relative aspect-[16/9] bg-[#12161d] grid place-items-center text-white/25 overflow-hidden">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={image} alt={`Preuve ${meta.label}`} className="h-full w-full object-cover" />
        ) : <ImageIcon className="h-9 w-9" strokeWidth={1.4} />}
        <span className="absolute left-3 top-3 rounded-os bg-black/65 px-2 py-1 text-[10px] font-semibold text-white">{meta.label}</span>
        <span className="absolute right-3 bottom-3 rounded-os bg-black/65 px-2 py-1 os-num text-[9px] text-white/85">{dateTime(event.timestamp, true)}</span>
      </div>
      <div className="p-4">
        <p className="text-[13px] font-semibold text-os-t1">{event.camera_nom}</p>
        <p className="mt-1 text-[11px] text-os-t3">{eventValue(event)}</p>
        <EvidenceDetails event={event} />
        <p className="mt-3 pt-3 border-t border-os-border text-[9px] text-os-t4">
          {event.snapshot_fallback === "vacancy_event" || event.meta?.snapshot_origin === "vacancy_frame_fallback"
            ? "Capture du début de l’absence · utilisée car aucune frame de clôture n’était disponible"
            : "Capture contextuelle de l’événement · aucune identification personnelle"}
        </p>
      </div>
    </Card>
  );
}

export default function PresencePage() {
  const [period, setPeriod] = useState(30);
  const [cameraId, setCameraId] = useState("all");
  const [scheduleId, setScheduleId] = useState("all");
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [absence, setAbsence] = useState(null);
  const [staffing, setStaffing] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [zones, setZones] = useState([]);
  const [workSchedules, setWorkSchedules] = useState([]);
  const [events, setEvents] = useState([]);
  const [live, setLive] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [calibrationCameraId, setCalibrationCameraId] = useState("");

  const loadLive = useCallback(async () => {
    try {
      const response = await fetch(`${CORE_URL}/api/staffing`, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      setLive(Array.isArray(data?.cameras) ? data.cameras : []);
    } catch { /* Les données historiques restent visibles si le Core est indisponible. */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const cameraQuery = cameraId === "all" ? "" : `&camera_id=${encodeURIComponent(cameraId)}`;
    const scheduleQuery = scheduleId === "all" ? "" : `&work_schedule_id=${encodeURIComponent(scheduleId)}`;
    try {
      const [absenceRes, staffingRes, camerasRes, zonesRes, schedulesRes, eventsRes] = await Promise.all([
        fetchWithRefresh(`/api/analytics/post-absence?days=${period}${cameraQuery}${scheduleQuery}`),
        fetchWithRefresh(`/api/analytics/staffing?days=${period}${cameraQuery}${scheduleQuery}`),
        fetchWithRefresh("/api/cameras"), fetchWithRefresh("/api/zones"),
        fetchWithRefresh("/api/work-schedules?active_only=true"),
        fetchWithRefresh(`/api/presence-events?days=${period}&page=1&page_size=40${cameraQuery}${scheduleQuery}`),
      ]);
      if (!absenceRes?.ok || !staffingRes?.ok) throw new Error("analytics");
      const [absenceData, staffingData, cameraData, zoneData, schedulesData, eventData] = await Promise.all([
        absenceRes.json(), staffingRes.json(), camerasRes?.ok ? camerasRes.json() : [],
        zonesRes?.ok ? zonesRes.json() : [], schedulesRes?.ok ? schedulesRes.json() : [],
        eventsRes?.ok ? eventsRes.json() : [],
      ]);
      setAbsence(absenceData); setStaffing(staffingData);
      setCameras(Array.isArray(cameraData) ? cameraData : []);
      setZones(Array.isArray(zoneData) ? zoneData : []);
      setWorkSchedules(Array.isArray(schedulesData) ? schedulesData : []);
      const scopedEvents = Array.isArray(eventData?.items) ? eventData.items : [];
      setEvents(attachClosureSnapshots(scopedEvents));
      await loadLive(); setUpdatedAt(new Date());
    } catch { setError("Impossible de charger toutes les données de présence."); }
    finally { setLoading(false); }
  }, [cameraId, loadLive, period, scheduleId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const timer = setInterval(loadLive, 8000); return () => clearInterval(timer); }, [loadLive]);
  useEffect(() => { setSelectedEventId(null); }, [cameraId, period, scheduleId]);

  const presenceZones = useMemo(() => zones.filter((zone) => zone.kind === "presence" && zone.is_active), [zones]);
  const scopedPresenceZones = useMemo(() => presenceZones.filter((zone) => (
    scheduleId === "all" || Number(zone.work_schedule_id) === Number(scheduleId)
  )), [presenceZones, scheduleId]);
  const monitoredCameras = useMemo(() => cameras
    .filter((camera) => scopedPresenceZones.some((zone) => Number(zone.camera_id) === Number(camera.id)))
    .sort((a, b) => a.cam_name.localeCompare(b.cam_name)), [cameras, scopedPresenceZones]);

  const rows = useMemo(() => {
    const liveMap = new Map(live.map((item) => [Number(item.camera_id), item]));
    const vacantMap = new Map();
    for (const post of absence?.current_posts || []) {
      const list = vacantMap.get(Number(post.camera_id)) || [];
      list.push(post); vacantMap.set(Number(post.camera_id), list);
    }
    const shortageMap = new Map((staffing?.current_cameras || []).map((item) => [Number(item.camera_id), item]));
    return monitoredCameras
      .filter((camera) => cameraId === "all" || String(camera.id) === String(cameraId))
      .map((camera) => {
        const rawCameraLive = liveMap.get(Number(camera.id));
        const cameraZones = scopedPresenceZones.filter((zone) => Number(zone.camera_id) === Number(camera.id));
        const allowedZoneIds = new Set(cameraZones.map((zone) => Number(zone.id)));
        const scopedLiveZones = (rawCameraLive?.presence_zones || []).filter((zone) => allowedZoneIds.has(Number(zone.zone_id)));
        const scopedPresenceState = aggregatePresenceState(scopedLiveZones);
        const staffingApplies = scheduleId === "all" || Number(rawCameraLive?.schedule_id) === Number(scheduleId);
        let scopedDecision = scheduleId === "all" ? rawCameraLive?.decision_state : scopedPresenceState;
        if (staffingApplies && ["staffing_low", "staffing_pending"].includes(rawCameraLive?.staffing_state)) scopedDecision = rawCameraLive.staffing_state;
        const cameraLive = rawCameraLive ? { ...rawCameraLive, presence_zones: scopedLiveZones, presence_state: scopedPresenceState, decision_state: scopedDecision } : null;
        const vacant = vacantMap.get(Number(camera.id)) || [];
        const shortage = shortageMap.get(Number(camera.id));
        let status = "pending";
        const decision = cameraLive?.decision_state;
        if (!camera.is_active || (cameraLive && !cameraLive.monitoring_available)) status = "unavailable";
        else if (!cameraLive) status = "pending";
        else if (decision === "staffing_low" || shortage || cameraLive.low) status = "low";
        else if (decision === "staffing_pending") status = "staffing_pending";
        else if (decision === "vacant") status = "vacant";
        else if (decision === "confirming") status = "confirming";
        else if (decision === "vacancy_pending") status = "vacancy_pending";
        else if (decision === "off_schedule") status = "off_schedule";
        else if (decision === "unconfigured") status = "unconfigured";
        else if (decision === "occupied" || decision === "staffed" || decision === "observing") status = "ok";
        else if (vacant.length) status = "vacant";
        else status = "pending";
        return { camera, live: cameraLive, zones: cameraZones, vacant, shortage, status };
      });
  }, [absence, cameraId, live, monitoredCameras, scheduleId, scopedPresenceZones, staffing]);

  useEffect(() => {
    if (rows.length && !rows.some((row) => String(row.camera.id) === String(calibrationCameraId))) {
      setCalibrationCameraId(String(rows[0].camera.id));
    }
  }, [calibrationCameraId, rows]);

  const totalAgents = rows.reduce((sum, row) => sum + (Number(row.live?.count) || 0), 0);
  const totalPosts = rows.reduce((sum, row) => sum + row.zones.length, 0);
  const liveCameras = rows.filter((row) => row.live?.camera_state === "online").length;
  const currentVacant = rows.reduce((sum, row) => {
    if (!row.live?.monitoring_available) return sum;
    const liveZones = row.live.presence_zones || [];
    const liveVacant = liveZones.filter((zone) => zone.state === "vacant").length;
    return sum + (liveZones.length ? liveVacant : row.vacant.length);
  }, 0);
  const currentShortages = rows.filter((row) => row.live?.monitoring_available && row.status === "low").length;
  const openItems = rows.flatMap((row) => {
    if (!row.live?.monitoring_available) return [];
    const items = [];
    if (row.live.low) items.push({
      key: `staff-${row.camera.id}`, kind: "Sous-effectif", name: row.camera.cam_name,
      value: `${row.live.count ?? 0}/${row.live.maximum ?? "—"} agents`,
      since: row.live.low_since, color: "var(--os-red)",
    });
    for (const zone of row.live.presence_zones || []) {
      if (zone.state !== "vacant") continue;
      items.push({
        key: `post-${row.camera.id}-${zone.zone_id}`, kind: "Poste vacant",
        name: zone.zone_name || "Poste", value: `${row.camera.cam_name} · ${duration(zone.vacant_for_s)}`,
        since: zone.vacant_since, color: "var(--os-amber)",
      });
    }
    return items;
  });
  const selectedEvent = events.find((event) => Number(event.id) === Number(selectedEventId)) || events.find((event) => event.snapshot_url) || events[0] || null;
  const historyQuery = new URLSearchParams({ days: String(period) });
  if (cameraId !== "all") historyQuery.set("camera_id", cameraId);
  if (scheduleId !== "all") historyQuery.set("work_schedule_id", scheduleId);
  const historyHref = `/Osirion/admin/presence/history?${historyQuery.toString()}`;

  return (
    <OsShell>
      <div className="p-6">
        <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-[22px] font-bold text-os-t1 leading-tight">Présence des agents</h1>
            <p className="text-[13px] text-os-t3 mt-0.5">Vue décisionnelle des postes et effectifs réellement surveillés</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <Segmented value={period} onChange={setPeriod} options={PERIODS} size="sm" />
            <select value={scheduleId} onChange={(event) => { setScheduleId(event.target.value); setCameraId("all"); }} className="h-9 min-w-52 rounded-os border border-os-border bg-os-card px-3 text-[12px] text-os-t1 outline-none focus:border-os-t3">
              <option value="all">Tous les groupes / pays</option>
              {workSchedules.map((schedule) => <option key={schedule.id} value={schedule.id}>{schedule.name}</option>)}
            </select>
            <select value={cameraId} onChange={(event) => setCameraId(event.target.value)} className="h-9 min-w-56 rounded-os border border-os-border bg-os-card px-3 text-[12px] text-os-t1 outline-none focus:border-os-t3">
              <option value="all">Toutes les caméras avec poste agent</option>
              {monitoredCameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.cam_name}</option>)}
            </select>
            <RefreshButton onClick={load} spinning={loading} />
          </div>
        </div>

        {error && <p className="mb-4 rounded-os border border-os-red/30 bg-os-red/5 px-4 py-3 text-[12px] text-os-red">{error}</p>}

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-4">
          <Kpi icon={UsersRound} label="Agents observés" value={totalAgents} hint={`${liveCameras}/${rows.length} caméra(s) remontent des données`} />
          <Kpi icon={Camera} label="Postes suivis" value={totalPosts} hint={`${liveCameras}/${rows.length} caméra(s) exploitables`} tone="good" />
          <Kpi icon={UserMinus} label="Postes vacants" value={currentVacant} hint={`${absence?.closed_episodes || 0} épisode(s) clôturé(s) sur ${period} j`} tone={currentVacant ? "bad" : "good"} />
          <Kpi icon={AlertTriangle} label="Sous-effectifs" value={currentShortages} hint={`${staffing?.closed_episodes || 0} épisode(s) clôturé(s) sur ${period} j`} tone={currentShortages ? "bad" : "good"} />
        </div>

        {!loading && monitoredCameras.length === 0 ? (
          <Card><EmptyState icon={UserRoundCheck}>Aucune caméra ne possède de zone active « Poste d&apos;agent » pour ce groupe.</EmptyState></Card>
        ) : (
          <>
            <StatusDistribution rows={rows} />
            <LivePostStates rows={rows} />
            <CalibrationPanel rows={rows} cameraId={calibrationCameraId} onCameraChange={setCalibrationCameraId} />

            <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-4">
              <Card className="overflow-hidden">
                <div className="px-5 py-4 border-b border-os-border">
                  <h2 className="text-[14px] font-semibold text-os-t1">Durée quotidienne des incidents</h2>
                  <p className="text-[11px] text-os-t3">Évolution des minutes d&apos;absence et de sous-effectif</p>
                </div>
                <DurationTrend absence={absence} staffing={staffing} />
              </Card>
              <Card className="px-4 py-1">
                <PeriodStat label="Temps d'absence cumulé — tous postes" value={duration(absence?.total_absence_s)} hint={`${absence?.affected_posts || 0} poste(s) touché(s) · données fiables${absence?.data_quality?.reliable_since ? ` depuis ${dateTime(absence.data_quality.reliable_since)}` : " uniquement"}`} />
                <PeriodStat label="Absence moyenne" value={duration(absence?.avg_absence_s)} />
                <PeriodStat label="Absence la plus longue" value={duration(absence?.max_absence_s)} />
                <PeriodStat label="Sous-effectif cumulé" value={duration(staffing?.total_shortage_s)} hint={`${staffing?.affected_cameras || 0} caméra(s) touchée(s)`} />
                <PeriodStat label="Sous-effectif moyen" value={duration(staffing?.avg_shortage_s)} />
                <PeriodStat label="Sous-effectif maximal" value={duration(staffing?.max_shortage_s)} />
              </Card>
            </div>

            <GroupAnalytics absence={absence} staffing={staffing} schedules={workSchedules} />

            <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4 mt-4">
              <Card className="overflow-hidden">
                <div className="px-5 py-4 border-b border-os-border flex flex-wrap items-center justify-between gap-3">
                  <div><h2 className="text-[14px] font-semibold text-os-t1">Fréquence des incidents</h2><p className="text-[11px] text-os-t3">Nombre d&apos;épisodes sur les 14 derniers jours</p></div>
                  <div className="flex gap-3 text-[10px] text-os-t3"><span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-os-amber" /> Absence</span><span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-os-red" /> Sous-effectif</span></div>
                </div>
                <IncidentBars absence={absence} staffing={staffing} />
              </Card>
              <Card className="overflow-hidden">
                <div className="px-5 py-4 border-b border-os-border"><h2 className="text-[14px] font-semibold text-os-t1">À traiter maintenant</h2><p className="text-[11px] text-os-t3">Situations encore ouvertes</p></div>
                <div className="divide-y divide-os-border max-h-72 overflow-y-auto">
                  {openItems.length ? openItems.map((item) => (
                    <div key={item.key} className="px-4 py-3 flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full shrink-0" style={{ background: item.color }} />
                      <div className="min-w-0 flex-1"><p className="text-[11px] font-semibold" style={{ color: item.color }}>{item.kind}</p><p className="text-[12px] font-semibold text-os-t1 truncate">{item.name}</p><p className="text-[11px] text-os-t3 truncate">{item.value}</p></div>
                      <span className="os-num text-[10px] text-os-t4 whitespace-nowrap">{elapsed(item.since)}</span>
                    </div>
                  )) : <EmptyState icon={CheckCircle2}>Aucune situation ouverte.</EmptyState>}
                </div>
              </Card>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[0.95fr_1.05fr] gap-4 mt-4 items-start">
              <Card className="overflow-hidden">
                <div className="px-5 py-4 border-b border-os-border flex items-center justify-between gap-3">
                  <div><h2 className="text-[14px] font-semibold text-os-t1">Journal de présence</h2><p className="text-[11px] text-os-t3">Derniers changements significatifs</p></div>
                  <Link href={historyHref} className="text-[11px] font-semibold text-os-t2 hover:text-os-t1">Historique complet</Link>
                </div>
                <div className="divide-y divide-os-border max-h-80 overflow-y-auto">
                  {events.slice(0, 12).map((event) => {
                    const meta = EVENT_META[event.event_type] || { label: event.event_type, color: "var(--os-t3)" };
                    const selected = selectedEvent?.id === event.id;
                    return (
                      <button key={event.id} onClick={() => setSelectedEventId(event.id)} className={`w-full px-4 py-3 text-left flex items-start gap-3 transition-colors ${selected ? "bg-os-primary/10" : "hover:bg-black/[0.02]"}`}>
                        <span className="mt-1 h-2 w-2 rounded-full shrink-0" style={{ background: meta.color }} />
                        <div className="min-w-0 flex-1"><p className="text-[11px] font-semibold" style={{ color: meta.color }}>{meta.label}</p><p className="text-[12px] font-medium text-os-t1 truncate">{event.camera_nom}</p><p className="text-[10px] text-os-t3 truncate">{eventValue(event)}</p></div>
                        <span className="os-num text-[9px] text-os-t4 whitespace-nowrap">{dateTime(event.timestamp)}</span>
                      </button>
                    );
                  })}
                  {!events.length && <EmptyState icon={Clock3}>Aucun événement sur la période.</EmptyState>}
                </div>
              </Card>
              <EventEvidence event={selectedEvent} />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
              <Card className="p-5">
                <h2 className="text-[14px] font-semibold text-os-t1">Postes les plus touchés</h2><p className="text-[11px] text-os-t3 mb-4">Durée d&apos;absence cumulée</p>
                {(absence?.zones || []).slice(0, 6).length ? absence.zones.slice(0, 6).map((zone, index) => {
                  const max = Math.max(1, ...(absence.zones || []).map((item) => item.total_absence_s || 0));
                  return <div key={`${zone.zone_id}-${zone.work_schedule_id || "none"}`} className="mb-3 last:mb-0"><div className="flex justify-between gap-3 text-[11px]"><span className="text-os-t2 truncate"><b className="os-num mr-2 text-os-t4">{index + 1}</b>{zone.zone_name} · {zone.camera_name}</span><span className="os-num text-os-t3 whitespace-nowrap">{duration(zone.total_absence_s)}</span></div><div className="mt-1.5 h-1 rounded-full bg-os-card-2"><div className="h-full rounded-full bg-os-amber" style={{ width: `${Math.max(3, (zone.total_absence_s / max) * 100)}%` }} /></div></div>;
                }) : <p className="text-[12px] text-os-t3">Aucune absence clôturée sur cette période.</p>}
              </Card>
              <Card className="p-5">
                <h2 className="text-[14px] font-semibold text-os-t1">Caméras les plus touchées</h2><p className="text-[11px] text-os-t3 mb-4">Durée de sous-effectif cumulée</p>
                {(staffing?.cameras || []).slice(0, 6).length ? staffing.cameras.slice(0, 6).map((camera, index) => {
                  const max = Math.max(1, ...(staffing.cameras || []).map((item) => item.total_shortage_s || 0));
                  return <div key={`${camera.camera_id}-${camera.work_schedule_id || "none"}`} className="mb-3 last:mb-0"><div className="flex justify-between gap-3 text-[11px]"><span className="text-os-t2 truncate"><b className="os-num mr-2 text-os-t4">{index + 1}</b>{camera.camera_name}{camera.site ? ` · ${camera.site}` : ""}</span><span className="os-num text-os-t3 whitespace-nowrap">{duration(camera.total_shortage_s)}</span></div><div className="mt-1.5 h-1 rounded-full bg-os-card-2"><div className="h-full rounded-full bg-os-red" style={{ width: `${Math.max(3, (camera.total_shortage_s / max) * 100)}%` }} /></div></div>;
                }) : <p className="text-[12px] text-os-t3">Aucun épisode de sous-effectif clôturé sur cette période.</p>}
              </Card>
            </div>

            <p className="mt-4 text-right os-num text-[9px] text-os-t4">Dernière actualisation : {updatedAt ? updatedAt.toLocaleTimeString("fr-FR") : "—"}</p>
          </>
        )}
      </div>
    </OsShell>
  );
}

"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, CheckCircle2, ChevronLeft, ChevronRight, Clock3,
  Image as ImageIcon, Search, ShieldAlert, UserMinus, UsersRound,
} from "lucide-react";
import OsShell from "../../_osirion/OsShell";
import { Card, EmptyState, PageHeader, RefreshButton, Segmented } from "../../_osirion/ui";
import { fetchWithRefresh } from "../../../../lib/fetchWithRefresh";

const PERIODS = [
  { value: 1, label: "Aujourd’hui" },
  { value: 7, label: "7 jours" },
  { value: 30, label: "30 jours" },
  { value: 90, label: "90 jours" },
];
const TYPES = {
  POST_VACANT: { label: "Poste vacant", color: "var(--os-red)", icon: UserMinus },
  POST_ABSENCE: { label: "Absence clôturée", color: "var(--os-amber)", icon: CheckCircle2 },
  STAFFING_LOW: { label: "Sous-effectif", color: "var(--os-red)", icon: ShieldAlert },
  STAFFING_RECOVERED: { label: "Effectif rétabli", color: "var(--os-green)", icon: UsersRound },
};
const RESOLUTION_REASONS = {
  presence_restored: "Agent revenu au poste",
  minimum_restored: "Effectif minimum rétabli",
  schedule_ended: "Fin du créneau de travail",
  camera_unavailable: "Caméra devenue indisponible",
  configuration_changed: "Configuration modifiée",
  schedule_changed: "Groupe horaire modifié",
  monitoring_suspended: "Surveillance suspendue",
};

function utcDate(value) {
  if (!value) return null;
  const raw = String(value);
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}
function time(value) {
  const date = utcDate(value);
  return date ? date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
}
function dayKey(value) {
  const date = utcDate(value);
  return date ? date.toLocaleDateString("fr-CA") : "unknown";
}
function dayLabel(value) {
  const date = utcDate(value);
  if (!date) return "Date inconnue";
  const today = new Date();
  const yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Aujourd’hui";
  if (date.toDateString() === yesterday.toDateString()) return "Hier";
  return date.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
}
function duration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}
function imageUrl(value) {
  if (!value) return null;
  return String(value).startsWith("http") ? value : `/api/images?path=${encodeURIComponent(value)}`;
}
function eventDescription(event) {
  const meta = event?.meta || {};
  if (event?.event_type === "POST_VACANT") return `${meta.zone_name || "Poste"} · vacant depuis ${duration(meta.vacant_s)}`;
  if (event?.event_type === "POST_ABSENCE") return `${meta.zone_name || "Poste"} · durée ${duration(meta.absence_s)}`;
  if (event?.event_type === "STAFFING_LOW") return `${meta.count ?? 0}/${meta.maximum ?? "—"} agents · ${meta.missing ?? "—"} manquant(s)`;
  return `Épisode de sous-effectif ${duration(meta.shortage_s)}`;
}

function SummaryCard({ type, count, active, onClick }) {
  const meta = TYPES[type];
  const Icon = meta.icon;
  return (
    <button onClick={onClick} className={`rounded-os border p-4 text-left transition-colors ${active ? "border-os-primary bg-os-primary/10" : "border-os-border bg-os-card hover:bg-os-card-2"}`}>
      <div className="flex items-start justify-between gap-3">
        <div><p className="text-[10px] font-semibold uppercase tracking-wide text-os-t3">{meta.label}</p><p className="os-num mt-2 text-[24px] font-bold text-os-t1">{count || 0}</p></div>
        <span className="h-9 w-9 rounded-os grid place-items-center" style={{ color: meta.color, background: `color-mix(in srgb, ${meta.color} 10%, transparent)` }}><Icon className="h-4 w-4" /></span>
      </div>
    </button>
  );
}

function Evidence({ event }) {
  if (!event) return <Card><EmptyState icon={ImageIcon}>Sélectionnez un événement.</EmptyState></Card>;
  const meta = event.meta || {};
  const type = TYPES[event.event_type] || { label: event.event_type, color: "var(--os-t3)" };
  const image = imageUrl(event.snapshot_url);
  const reason = RESOLUTION_REASONS[meta.resolution_reason];
  const decision = meta.decision || {};
  return (
    <Card className="overflow-hidden xl:sticky xl:top-4">
      <div className="relative aspect-[16/9] bg-[#12161d] grid place-items-center text-white/25 overflow-hidden">
        {image ? <img src={image} alt={`Preuve ${type.label}`} className="h-full w-full object-cover" /> : <ImageIcon className="h-10 w-10" strokeWidth={1.3} />}
        <span className="absolute left-3 top-3 rounded-os bg-black/70 px-2 py-1 text-[10px] font-semibold text-white">{type.label}</span>
        <span className="absolute right-3 bottom-3 rounded-os bg-black/70 px-2 py-1 os-num text-[9px] text-white">{time(event.timestamp)}</span>
      </div>
      <div className="p-4">
        <p className="text-[14px] font-semibold text-os-t1">{event.camera_nom}</p>
        <p className="text-[11px] text-os-t3">{event.camera_location || "Emplacement non renseigné"}</p>
        <p className="mt-3 text-[12px] font-medium text-os-t2">{eventDescription(event)}</p>
        <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-os-border pt-4">
          <div><dt className="text-[9px] text-os-t4">Groupe / pays</dt><dd className="mt-0.5 text-[11px] font-semibold text-os-t2">{meta.schedule_name || "—"}</dd></div>
          <div><dt className="text-[9px] text-os-t4">Cause de clôture</dt><dd className="mt-0.5 text-[11px] font-semibold text-os-t2">{reason || "—"}</dd></div>
          {decision.confirmed_count != null && <div><dt className="text-[9px] text-os-t4">Présences confirmées</dt><dd className="os-num mt-0.5 text-[11px] font-semibold text-os-t2">{decision.confirmed_count}</dd></div>}
          {decision.candidate_count != null && <div><dt className="text-[9px] text-os-t4">Candidats observés</dt><dd className="os-num mt-0.5 text-[11px] font-semibold text-os-t2">{decision.candidate_count}</dd></div>}
        </dl>
        {(() => {
          const caption = event.snapshot_fallback === "vacancy_event" || meta.snapshot_origin === "vacancy_frame_fallback"
            ? "Capture du début de l’absence, utilisée comme preuve de secours."
            : image ? "" : "Aucune capture disponible pour cet événement.";
          return caption ? <p className="mt-4 border-t border-os-border pt-3 text-[9px] text-os-t4">{caption}</p> : null;
        })()}
      </div>
    </Card>
  );
}

function HistoryContent() {
  const [days, setDays] = useState(30);
  const [type, setType] = useState("all");
  const [cameraId, setCameraId] = useState("all");
  const [scheduleId, setScheduleId] = useState("all");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0, pages: 1, summary: {} });
  const [cameras, setCameras] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initialDays = Number(params.get("days"));
    if ([1, 7, 30, 90].includes(initialDays)) setDays(initialDays);
    if (params.get("camera_id")) setCameraId(params.get("camera_id"));
    if (params.get("work_schedule_id")) setScheduleId(params.get("work_schedule_id"));
  }, []);

  useEffect(() => {
    Promise.all([fetchWithRefresh("/api/cameras"), fetchWithRefresh("/api/work-schedules?active_only=true")])
      .then(async ([cameraRes, scheduleRes]) => {
        setCameras(cameraRes?.ok ? await cameraRes.json() : []);
        setSchedules(scheduleRes?.ok ? await scheduleRes.json() : []);
      }).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const params = new URLSearchParams({ days: String(days), page: String(page), page_size: "20" });
    if (type !== "all") params.set("event_type", type);
    if (cameraId !== "all") params.set("camera_id", cameraId);
    if (scheduleId !== "all") params.set("work_schedule_id", scheduleId);
    if (appliedSearch) params.set("search", appliedSearch);
    if (includeArchived) params.set("include_archived", "true");
    try {
      const response = await fetchWithRefresh(`/api/presence-events?${params}`);
      if (!response?.ok) throw new Error("history");
      const payload = await response.json();
      setData(payload); setSelectedId((current) => payload.items?.some((item) => item.id === current) ? current : payload.items?.[0]?.id || null);
    } catch { setError("Impossible de charger l’historique de présence."); }
    finally { setLoading(false); }
  }, [appliedSearch, cameraId, days, includeArchived, page, scheduleId, type]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [appliedSearch, cameraId, days, includeArchived, scheduleId, type]);

  const selected = data.items?.find((item) => item.id === selectedId) || data.items?.[0] || null;
  const groups = useMemo(() => {
    const result = [];
    for (const event of data.items || []) {
      const key = dayKey(event.timestamp);
      let group = result.find((item) => item.key === key);
      if (!group) { group = { key, label: dayLabel(event.timestamp), events: [] }; result.push(group); }
      group.events.push(event);
    }
    return result;
  }, [data.items]);
  const selectClass = "h-10 rounded-os border border-os-border bg-os-card px-3 text-[12px] text-os-t1 outline-none focus:border-os-t3";

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader title="Historique de présence" subtitle={`${data.total || 0} événement(s) sur la période sélectionnée`} actions={<div className="flex items-center gap-2"><Link href="/Osirion/admin/presence" className="h-9 px-3 rounded-os border border-os-border inline-flex items-center gap-2 text-[11px] font-semibold text-os-t2 hover:text-os-t1"><ArrowLeft className="h-4 w-4" /> Tableau de bord</Link><RefreshButton onClick={load} spinning={loading} /></div>} />

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
          {Object.keys(TYPES).map((eventType) => <SummaryCard key={eventType} type={eventType} count={data.summary?.[eventType]} active={type === eventType} onClick={() => setType(type === eventType ? "all" : eventType)} />)}
        </div>

        <Card className="p-4 mb-4">
          <div className="flex flex-col xl:flex-row xl:items-center gap-3">
            <Segmented value={days} onChange={setDays} options={PERIODS} size="sm" />
            <select value={scheduleId} onChange={(event) => setScheduleId(event.target.value)} className={`${selectClass} xl:min-w-52`}><option value="all">Tous les groupes / pays</option>{schedules.map((schedule) => <option key={schedule.id} value={schedule.id}>{schedule.name}</option>)}</select>
            <select value={cameraId} onChange={(event) => setCameraId(event.target.value)} className={`${selectClass} xl:min-w-52`}><option value="all">Toutes les caméras</option>{cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.cam_name}</option>)}</select>
            <select value={type} onChange={(event) => setType(event.target.value)} className={`${selectClass} xl:min-w-44`}><option value="all">Tous les événements</option>{Object.entries(TYPES).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}</select>
            <form onSubmit={(event) => { event.preventDefault(); setAppliedSearch(search.trim()); }} className="flex min-w-0 flex-1 gap-2"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Poste, caméra, agence…" className={`${selectClass} min-w-0 flex-1`} /><button className="h-10 w-10 shrink-0 rounded-os bg-os-cta text-white grid place-items-center" aria-label="Rechercher"><Search className="h-4 w-4" /></button></form>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-os-border pt-3 text-[10px] text-os-t4"><label className="ml-auto inline-flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} className="accent-os-primary" /> Inclure les archives non fiables ({data.archived_total || 0})</label></div>
        </Card>

        {error && <p className="mb-4 rounded-os border border-os-red/30 bg-os-red/5 px-4 py-3 text-[12px] text-os-red">{error}</p>}
        <div className="grid grid-cols-1 xl:grid-cols-[1.05fr_0.95fr] gap-4 items-start">
          <Card className="overflow-hidden">
            {loading ? <EmptyState icon={Clock3}>Chargement de l’historique…</EmptyState> : !groups.length ? <EmptyState icon={Clock3}>Aucun événement ne correspond à ces filtres.</EmptyState> : groups.map((group) => (
              <section key={group.key}>
                <div className="sticky top-0 z-10 border-y border-os-border bg-os-card-2/95 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-os-t3 first:border-t-0">{group.label}</div>
                <div className="divide-y divide-os-border">{group.events.map((event) => {
                  const meta = TYPES[event.event_type] || { label: event.event_type, color: "var(--os-t3)" };
                  const active = selected?.id === event.id;
                  return <button key={event.id} onClick={() => setSelectedId(event.id)} className={`w-full p-4 text-left flex items-start gap-3 transition-colors ${active ? "bg-os-primary/10" : "hover:bg-black/[0.02]"}`}><span className="mt-1.5 h-2.5 w-2.5 rounded-full shrink-0" style={{ background: meta.color }} /><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="text-[11px] font-semibold" style={{ color: meta.color }}>{meta.label}</p>{event.data_quality === "archived" && <span className="rounded bg-os-amber/10 px-1.5 py-0.5 text-[8px] font-semibold uppercase text-os-amber">archive</span>}{event.snapshot_url && <ImageIcon className="h-3 w-3 text-os-t4" />}</div><p className="mt-0.5 text-[12px] font-semibold text-os-t1 truncate">{event.camera_nom}</p><p className="mt-0.5 text-[10px] text-os-t3 truncate">{eventDescription(event)}{event.meta?.schedule_name ? ` · ${event.meta.schedule_name}` : ""}</p></div><span className="os-num text-[10px] text-os-t4 whitespace-nowrap">{time(event.timestamp)}</span></button>;
                })}</div>
              </section>
            ))}
            <div className="border-t border-os-border px-4 py-3 flex items-center justify-between gap-3"><span className="os-num text-[10px] text-os-t4">Page {data.page || 1} sur {data.pages || 1}</span><div className="flex gap-2"><button disabled={(data.page || 1) <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))} className="h-8 px-3 rounded-os border border-os-border text-[11px] text-os-t2 inline-flex items-center gap-1 disabled:opacity-40"><ChevronLeft className="h-3.5 w-3.5" /> Précédent</button><button disabled={(data.page || 1) >= (data.pages || 1) || loading} onClick={() => setPage((value) => value + 1)} className="h-8 px-3 rounded-os border border-os-border text-[11px] text-os-t2 inline-flex items-center gap-1 disabled:opacity-40">Suivant <ChevronRight className="h-3.5 w-3.5" /></button></div></div>
          </Card>
          <Evidence event={selected} />
        </div>
      </div>
    </OsShell>
  );
}

export default function PresenceHistoryPage() {
  return <Suspense fallback={null}><HistoryContent /></Suspense>;
}

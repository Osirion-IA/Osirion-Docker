"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

// ── Icônes SVG inline (auto-contenues) ──────────────────────────────────────
const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IconRefresh = ({ className }) => (<Svg className={className}><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v5h-5" /></Svg>);
const IconSearch = ({ className }) => (<Svg className={className}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></Svg>);
const IconInbox = ({ className }) => (<Svg className={className}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5 5h14l3 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6z" /></Svg>);
const IconUser = ({ className }) => (<Svg className={className}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>);
const IconX = ({ className }) => (<Svg className={className}><path d="M18 6 6 18M6 6l12 12" /></Svg>);

// Type d'événement → libellé FR + badge (aligné backend).
const TYPE_META = {
  ENTRY:             { label: "Entrée",          badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
  EXIT:              { label: "Sortie",          badge: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300" },
  DETECTION:         { label: "Détection",       badge: "bg-gray-200 text-gray-700 dark:bg-gray-700/50 dark:text-gray-300" },
  ZONE_OCCUPANCY_CHANGED: { label: "Occupation", badge: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300" },
  CROWD_DETECTED:    { label: "Attroupement",    badge: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300" },
  LINE_CROSSED:      { label: "Franchissement",  badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" },
};

function snapSrc(url) {
  if (!url) return null;
  return String(url).startsWith("http") ? url : `/api/images?path=${encodeURIComponent(url)}`;
}
function fmtTime(ts) {
  const d = new Date(ts);
  if (isNaN(d)) return "—";
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function Lightbox({ event, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const src = snapSrc(event.snapshot_url);
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/85 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex flex-col items-center max-w-4xl w-full">
        <button onClick={onClose} className="absolute -top-3 -right-3 z-10 h-9 w-9 rounded-full bg-white dark:bg-gray-800 shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300">
          <IconX className="h-5 w-5" />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={`Événement #${event.id}`} className="max-h-[72vh] max-w-full rounded-2xl object-contain shadow-2xl" />
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white/10 backdrop-blur-sm border border-white/20 text-white/80 text-xs">
          <span>#{event.id}</span><span className="text-white/30">·</span>
          <span className="font-semibold text-white">{TYPE_META[event.event_type]?.label || event.event_type}</span>
          <span className="text-white/30">·</span><span>{event.camera_nom}</span>
          {event.person_nom && (<><span className="text-white/30">·</span><span className="font-semibold text-white">{event.person_nom}</span></>)}
          <span className="text-white/30">·</span><span>{fmtTime(event.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}

export default function EventsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [typeFilter, setTypeFilter] = useState("tous");
  const [cameraFilter, setCameraFilter] = useState("tous");
  const [search, setSearch] = useState("");
  const [lightbox, setLightbox] = useState(null);

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const res = await fetchWithRefresh("/api/events?limit=500");
      if (!res) return;
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFetchError(d?.message || "Erreur de chargement.");
        return;
      }
      const data = await res.json();
      setEvents(Array.isArray(data) ? data : []);
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  const cameras = useMemo(() => {
    const m = new Map();
    for (const e of events) if (!m.has(e.camera_id)) m.set(e.camera_id, e.camera_nom || `CAM-${e.camera_id}`);
    return Array.from(m, ([id, name]) => ({ id, name }));
  }, [events]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return events.filter((e) => {
      if (typeFilter !== "tous" && e.event_type !== typeFilter) return false;
      if (cameraFilter !== "tous" && String(e.camera_id) !== String(cameraFilter)) return false;
      if (q) {
        const hay = [e.event_type, e.camera_nom, e.camera_location, e.person_nom].filter(Boolean).join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [events, typeFilter, cameraFilter, search]);

  if (user && !["admin", "user", "viewer"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/events" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/events"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Événements"
            subtitle={`${filtered.length} événement(s) affiché(s)`}
            showSearch={false}
            actions={
              <button
                onClick={loadEvents}
                className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <IconRefresh className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Actualiser
              </button>
            }
          />

          <div className="p-6 space-y-6">
            {/* Filtres */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="tous">Tous les types</option>
                  {Object.entries(TYPE_META).map(([v, m]) => <option key={v} value={v}>{m.label}</option>)}
                </select>
                <select
                  value={cameraFilter}
                  onChange={(e) => setCameraFilter(e.target.value)}
                  className="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="tous">Toutes les caméras</option>
                  {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <div className="relative">
                  <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Personne, lieu…"
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 pl-9 pr-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
            </div>

            {/* Liste */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
              {fetchError ? (
                <div className="p-10 text-center">
                  <p className="text-sm text-rose-600 dark:text-rose-400">{fetchError}</p>
                  <button onClick={loadEvents} className="mt-3 text-sm font-medium text-indigo-600 hover:underline">Réessayer</button>
                </div>
              ) : loading ? (
                <div className="p-10 text-center text-sm text-gray-500 dark:text-gray-400">
                  <IconRefresh className="h-6 w-6 mx-auto mb-3 animate-spin opacity-60" /> Chargement…
                </div>
              ) : filtered.length === 0 ? (
                <div className="p-12 text-center">
                  <IconInbox className="h-10 w-10 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {events.length === 0 ? "Aucun événement enregistré." : "Aucun événement ne correspond aux filtres."}
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {filtered.map((e) => {
                    const meta = TYPE_META[e.event_type] || { label: e.event_type, badge: "bg-gray-200 text-gray-700 dark:bg-gray-700/50 dark:text-gray-300" };
                    const src = snapSrc(e.snapshot_url);
                    const detail = e.meta
                      ? ([e.meta.zone_name || e.meta.line_name,
                          e.meta.count != null ? `${e.meta.count} pers.` : null,
                          e.meta.direction ? (e.meta.direction === "in" ? "entrée" : "sortie") : null]
                          .filter(Boolean).join(" · ") || "—")
                      : "—";
                    return (
                      <li key={e.id} className="flex items-center gap-4 p-4 hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors">
                        <button
                          onClick={() => src && setLightbox(e)}
                          className={`shrink-0 h-14 w-14 rounded-xl bg-gray-100 dark:bg-gray-800 overflow-hidden flex items-center justify-center text-gray-400 ${src ? "cursor-zoom-in" : ""}`}
                        >
                          {src ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={src} alt="snapshot" className="h-full w-full object-cover" />
                          ) : <IconUser className="h-6 w-6" />}
                        </button>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${meta.badge}`}>{meta.label}</span>
                            <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">{detail}</span>
                          </div>
                          <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">
                            {e.camera_nom || `CAM-${e.camera_id}`}{e.camera_location ? ` · ${e.camera_location}` : ""} · {fmtTime(e.timestamp)}
                            {e.confidence != null ? ` · ${Math.round(e.confidence * 100)}%` : ""}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </main>
      </div>

      {lightbox && <Lightbox event={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}

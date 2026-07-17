"use client";

/**
 * Santé des caméras — page temps réel.
 *
 * Les métriques (état, FPS, reconnexions, viewers…) vivent dans le Core (moteur
 * de surveillance). On interroge son endpoint /api/cameras/health (CORS activé)
 * directement depuis le navigateur, exactement comme GpuMonitor pour /api/gpu.
 * Aucune dépendance nouvelle : sparkline SVG inline + polling.
 */

import { useState, useEffect, useRef } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { CORE_URL } from "../../../lib/publicUrls";

const POLL_MS = 2000;
const MAX_POINTS = 30;       // ~1 min d'historique FPS à 2 s/échantillon
const FPS_SCALE = 30;        // échelle haute de la sparkline (fps)

// ── Métadonnées d'état (label + couleurs) ───────────────────────────────────
const STATES = {
  online:     { label: "En ligne",    dot: "bg-emerald-500", badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300", spark: "#10b981" },
  stalled:    { label: "Figée",       dot: "bg-orange-500",  badge: "bg-orange-500/15 text-orange-600 dark:text-orange-300",   spark: "#f97316" },
  connecting: { label: "Connexion…",  dot: "bg-amber-500",   badge: "bg-amber-500/15 text-amber-600 dark:text-amber-300",     spark: "#f59e0b" },
  offline:    { label: "Hors ligne",  dot: "bg-rose-500",    badge: "bg-rose-500/15 text-rose-600 dark:text-rose-300",         spark: "#ef4444" },
  stopped:    { label: "Arrêtée",     dot: "bg-gray-400",    badge: "bg-gray-500/15 text-gray-600 dark:text-gray-300",         spark: "#9ca3af" },
};
const stateMeta = (s) => STATES[s] || STATES.stopped;

function fmtAge(sec) {
  if (sec === null || sec === undefined) return "—";
  if (sec < 60) return `${sec.toFixed(0)} s`;
  const m = Math.floor(sec / 60);
  return `${m} min ${Math.floor(sec % 60)} s`;
}
function fmtUptime(sec) {
  if (!sec) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

// Sparkline SVG (aire + ligne), 0..FPS_SCALE.
function Sparkline({ data, color, height = 44 }) {
  if (!data || data.length === 0) return <div style={{ height }} />;
  const w = 100, h = 100;
  const n = data.length;
  const step = n > 1 ? w / (n - 1) : w;
  const pts = data.map((v, i) => {
    const y = h - (Math.max(0, Math.min(FPS_SCALE, v)) / FPS_SCALE) * h;
    return `${(i * step).toFixed(2)},${y.toFixed(2)}`;
  });
  const line = pts.join(" ");
  const area = `0,${h} ${line} ${((n - 1) * step).toFixed(2)},${h}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: "100%", height }} className="block">
      <polyline points={area} fill={color} fillOpacity="0.12" stroke="none" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2"
                vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// Petite métrique (label + valeur) dans la grille d'une carte.
const Metric = ({ label, value, accent }) => (
  <div>
    <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
    <div className={`text-sm font-semibold ${accent || "text-gray-900 dark:text-white"}`}>{value}</div>
  </div>
);

export default function CamerasHealthPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [status, setStatus] = useState("loading");  // loading | ok | error
  const [summary, setSummary] = useState({ count: 0, online: 0 });
  const [cameras, setCameras] = useState([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const histRef = useRef({});  // cam_id -> [fps, ...]

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  useEffect(() => {
    let active = true;
    let timer = null;

    const poll = async () => {
      try {
        const res = await fetch(`${CORE_URL}/api/cameras/health`, { cache: "no-store" });
        if (!active) return;
        if (!res.ok) { setStatus("error"); return; }
        const data = await res.json();
        if (!active) return;
        const cams = data.cameras || [];
        for (const c of cams) {
          const arr = histRef.current[c.id] || [];
          arr.push(typeof c.fps === "number" ? c.fps : 0);
          if (arr.length > MAX_POINTS) arr.shift();
          histRef.current[c.id] = arr;
        }
        setCameras(cams);
        setSummary({ count: data.count || cams.length, online: data.online || 0 });
        setStatus("ok");
      } catch {
        if (active) setStatus("error");
      } finally {
        if (active && autoRefresh) timer = setTimeout(poll, POLL_MS);
      }
    };

    poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [autoRefresh]);

  return (
    <div className="min-h-screen bg-gray-50/70 dark:bg-gray-950">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((p) => !p)}
          currentPath="/Osirion/admin/cameras-health"
        />

        <main className={`flex-1 transition-all duration-300 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Santé des caméras"
            subtitle={status === "ok" ? `${summary.online}/${summary.count} en ligne` : "—"}
            showSearch={false}
            actions={
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={() => setAutoRefresh((v) => !v)}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <span className="text-gray-600 dark:text-gray-300">Auto (2s)</span>
              </label>
            }
          />

          <div className="p-5 lg:p-8 space-y-6">
            {status === "error" && (
              <div className="rounded-xl bg-amber-50/80 p-4 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800/50">
                Métriques indisponibles — Core injoignable sur {CORE_URL}.
              </div>
            )}

            {status === "loading" && (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400">Lecture de la santé des caméras…</div>
            )}

            {status !== "loading" && cameras.length === 0 && (
              <div className="rounded-2xl border bg-white/70 p-10 text-center text-gray-500 dark:text-gray-400 dark:border-gray-800 dark:bg-gray-900/60">
                Aucune caméra active. Ajoutez/activez une caméra : elle apparaîtra ici automatiquement (prise en compte à chaud).
              </div>
            )}

            {cameras.length > 0 && (
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
                {cameras.map((c) => {
                  const meta = stateMeta(c.state);
                  const hist = histRef.current[c.id] || [];
                  const degraded = c.reconnection_attempts > 0 && c.state !== "online";
                  return (
                    <div key={c.id} className="rounded-2xl border bg-white/70 p-5 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                      {/* En-tête : nom + état */}
                      <div className="flex items-start justify-between gap-3 mb-4">
                        <div className="min-w-0">
                          <div className="font-semibold text-gray-900 dark:text-white truncate">{c.name || `Caméra ${c.id}`}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{c.location || "—"} · #{c.id}</div>
                        </div>
                        <span className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${meta.badge}`}>
                          <span className={`h-2 w-2 rounded-full ${meta.dot} ${c.state === "online" ? "animate-pulse" : ""}`} />
                          {meta.label}
                        </span>
                      </div>

                      {/* FPS + sparkline */}
                      <div className="flex items-end justify-between mb-1">
                        <div className="text-3xl font-bold tabular-nums" style={{ color: meta.spark }}>
                          {(c.fps ?? 0).toFixed(1)}
                          <span className="text-sm font-medium text-gray-400 ml-1">fps</span>
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">{c.source_kind || "—"}</div>
                      </div>
                      <Sparkline data={hist} color={meta.spark} />

                      {/* Métriques détaillées */}
                      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                        <Metric label="Frames" value={(c.frames_captured ?? 0).toLocaleString("fr-FR")} />
                        <Metric
                          label="Reconnexions"
                          value={c.reconnections ?? 0}
                          accent={c.reconnections > 0 ? "text-amber-600 dark:text-amber-400" : undefined}
                        />
                        <Metric label="Dernière frame" value={fmtAge(c.last_frame_age_s)} />
                        <Metric label="Spectateurs" value={c.viewers ?? 0} />
                        <Metric label="Uptime" value={fmtUptime(c.uptime_s)} />
                        <Metric
                          label="Threads"
                          value={c.threads_alive ? "actifs" : "arrêtés"}
                          accent={c.threads_alive ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}
                        />
                      </div>

                      {degraded && (
                        <div className="mt-4 rounded-lg bg-amber-50/80 px-3 py-2 text-xs text-amber-700 border border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40">
                          Reconnexion en cours — {c.reconnection_attempts} tentative(s) consécutive(s).
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

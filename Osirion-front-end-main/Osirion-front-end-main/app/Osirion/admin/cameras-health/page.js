"use client";

/**
 * Santé des caméras traitées — section Configurer (thème clair). Métriques temps
 * réel lues DIRECTEMENT depuis le Core (CORE_URL/api/cameras/health) : état, FPS,
 * reconnexions, uptime, spectateurs. Les caméras sont REGROUPÉES PAR SITE (croisé
 * avec le catalogue backend) ; les caméras HikCentral offrent un bouton « Relancer »
 * (ré-interroge HikCentral) car les liaisons agences sont parfois instables.
 * Sparkline SVG inline + polling 2 s.
 */
import { useState, useEffect, useRef, useMemo } from "react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, EmptyState } from "../_osirion/ui";
import { Video, RotateCw } from "lucide-react";
import { CORE_URL } from "../../../lib/publicUrls";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { groupCamerasBySite } from "../../../lib/cameraGroups";

const POLL_MS = 2000, MAX_POINTS = 30, FPS_SCALE = 30;
const STATES = {
  online: { label: "En ligne", color: "var(--os-green)" },
  stalled: { label: "Figée", color: "var(--os-amber)" },
  connecting: { label: "Connexion…", color: "var(--os-amber)" },
  offline: { label: "Hors ligne", color: "var(--os-red)" },
  stopped: { label: "Arrêtée", color: "var(--os-t4)" },
};
const stateMeta = (s) => STATES[s] || STATES.stopped;
const fmtAge = (s) => (s == null ? "—" : s < 60 ? `${s.toFixed(0)} s` : `${Math.floor(s / 60)} min ${Math.floor(s % 60)} s`);
const fmtUptime = (s) => (!s ? "—" : Math.floor(s / 3600) > 0 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : `${Math.floor(s / 60)} min`);

function Sparkline({ data, color, height = 44 }) {
  if (!data || data.length === 0) return <div style={{ height }} />;
  const w = 100, h = 100, n = data.length, step = n > 1 ? w / (n - 1) : w;
  const pts = data.map((v, i) => `${(i * step).toFixed(2)},${(h - (Math.max(0, Math.min(FPS_SCALE, v)) / FPS_SCALE) * h).toFixed(2)}`);
  const line = pts.join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: "100%", height }} className="block">
      <polyline points={`0,${h} ${line} ${((n - 1) * step).toFixed(2)},${h}`} fill={color} fillOpacity="0.12" stroke="none" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
const Metric = ({ label, value, color }) => (
  <div>
    <div className="text-[10px] uppercase tracking-wide text-os-t4">{label}</div>
    <div className="text-[13px] font-semibold os-num" style={{ color: color || "var(--os-t1)" }}>{value}</div>
  </div>
);

export default function CamerasHealthPage() {
  const [status, setStatus] = useState("loading");
  const [summary, setSummary] = useState({ count: 0, online: 0 });
  const [cameras, setCameras] = useState([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [meta, setMeta] = useState({});        // id → { source_type, group_ids, cam_name }
  const [groups, setGroups] = useState([]);
  const [retry, setRetry] = useState({});      // id → { state: "pending"|"ok"|"err", msg }
  const histRef = useRef({});

  // Catalogue backend (source_type + site) — croisé avec la santé Core. Rafraîchi
  // à l'entrée puis toutes les 30 s (le catalogue bouge peu).
  useEffect(() => {
    let active = true;
    const load = async () => {
      const [cr, gr] = await Promise.all([
        fetchWithRefresh("/api/cameras"),
        fetchWithRefresh("/api/groups"),
      ]);
      if (!active) return;
      if (cr?.ok) {
        const list = await cr.json();
        const m = {};
        for (const c of Array.isArray(list) ? list : []) {
          m[c.id] = { source_type: c.source_type, group_ids: c.group_ids || [], cam_name: c.cam_name };
        }
        setMeta(m);
      }
      if (gr?.ok) { const g = await gr.json(); setGroups(Array.isArray(g) ? g : []); }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { active = false; clearInterval(t); };
  }, []);

  useEffect(() => {
    let active = true, timer = null;
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
      } catch { if (active) setStatus("error"); }
      finally { if (active && autoRefresh) timer = setTimeout(poll, POLL_MS); }
    };
    poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [autoRefresh]);

  const doRetry = async (id) => {
    setRetry((r) => ({ ...r, [id]: { state: "pending", msg: "" } }));
    try {
      const res = await fetchWithRefresh(`/api/hikcentral/cameras/${id}/retry`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) setRetry((r) => ({ ...r, [id]: { state: "ok", msg: "Flux ré-interrogé." } }));
      else setRetry((r) => ({ ...r, [id]: { state: "err", msg: data?.detail || data?.message || "Échec." } }));
    } catch {
      setRetry((r) => ({ ...r, [id]: { state: "err", msg: "Erreur réseau." } }));
    }
    setTimeout(() => setRetry((r) => { const n = { ...r }; delete n[id]; return n; }), 5000);
  };

  // Enrichit chaque caméra santé (Core) avec son site + type (backend) puis regroupe.
  const sites = useMemo(() => {
    const enriched = cameras.map((c) => ({
      ...c,
      cam_name: c.name || meta[c.id]?.cam_name,
      group_ids: meta[c.id]?.group_ids || [],
      source_type: meta[c.id]?.source_type,
    }));
    return groupCamerasBySite(enriched, groups);
  }, [cameras, meta, groups]);

  const renderCard = (c) => {
    const m = stateMeta(c.state);
    const hist = histRef.current[c.id] || [];
    const degraded = c.reconnection_attempts > 0 && c.state !== "online";
    const isHik = c.source_type === "hikcentral";
    const rt = retry[c.id];
    const attention = c.state === "offline" || c.state === "stalled" || c.state === "connecting";
    return (
      <Card key={c.id} className="p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <div className="text-[14px] font-semibold text-os-t1 truncate">{c.name || `Caméra ${c.id}`}</div>
            <div className="os-num text-[11px] text-os-t3 truncate">{c.location || "—"} · #{c.id}</div>
          </div>
          <span className="shrink-0 inline-flex items-center gap-1.5 text-[12px] font-medium" style={{ color: m.color }}>
            <span className={`h-2 w-2 rounded-full ${c.state === "online" ? "os-anim-pulse" : ""}`} style={{ background: m.color }} />{m.label}
          </span>
        </div>
        <div className="flex items-end justify-between mb-1">
          <div className="os-num text-[28px] font-bold leading-none" style={{ color: m.color }}>{(c.fps ?? 0).toFixed(1)}<span className="text-[13px] font-medium text-os-t4 ml-1">fps</span></div>
          <div className="text-[11px] text-os-t4">{c.source_kind || (isHik ? "HikCentral" : "—")}</div>
        </div>
        <Sparkline data={hist} color={m.color} />
        <div className="mt-4 grid grid-cols-3 gap-x-4 gap-y-3">
          <Metric label="Frames" value={(c.frames_captured ?? 0).toLocaleString("fr-FR")} />
          <Metric label="Reconnexions" value={c.reconnections ?? 0} color={c.reconnections > 0 ? "var(--os-amber)" : undefined} />
          <Metric label="Dernière" value={fmtAge(c.last_frame_age_s)} />
          <Metric label="Spectateurs" value={c.viewers ?? 0} />
          <Metric label="Uptime" value={fmtUptime(c.uptime_s)} />
          <Metric label="Threads" value={c.threads_alive ? "actifs" : "arrêtés"} color={c.threads_alive ? "var(--os-green)" : "var(--os-red)"} />
        </div>
        {degraded && <p className="mt-4 rounded-os border border-os-border bg-os-card-2 px-3 py-2 text-[12px] text-os-amber">Reconnexion — {c.reconnection_attempts} tentative(s).</p>}
        {isHik && (
          <div className="mt-4 flex items-center justify-between gap-3 border-t border-os-border pt-3">
            {rt?.state === "ok" ? (
              <span className="text-[12px] text-os-green">{rt.msg}</span>
            ) : rt?.state === "err" ? (
              <span className="text-[12px] text-os-red truncate" title={rt.msg}>{rt.msg}</span>
            ) : (
              <span className="text-[12px] text-os-t4">{attention ? "Liaison instable ?" : "Source HikCentral"}</span>
            )}
            <button
              onClick={() => doRetry(c.id)}
              disabled={rt?.state === "pending"}
              className={`shrink-0 inline-flex items-center gap-1.5 rounded-os px-3 py-1.5 text-[12px] font-medium border disabled:opacity-50 ${
                attention ? "border-transparent bg-os-cta text-white hover:bg-os-cta-hover" : "border-os-border text-os-t2 hover:text-os-t1"
              }`}
            >
              <RotateCw className={`h-3.5 w-3.5 ${rt?.state === "pending" ? "os-anim-spin" : ""}`} /> Relancer
            </button>
          </div>
        )}
      </Card>
    );
  };

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Santé des caméras traitées"
          subtitle={status === "ok" ? `${summary.online}/${summary.count} en ligne · métriques Core temps réel` : "Métriques Core temps réel"}
          actions={<label className="flex items-center gap-2 text-[13px] text-os-t2"><input type="checkbox" checked={autoRefresh} onChange={() => setAutoRefresh((v) => !v)} /> Auto (2s)</label>}
        />

        {status === "error" && (
          <Card className="p-4 mb-4"><p className="text-[13px] text-os-amber">Métriques indisponibles — Core injoignable sur {CORE_URL}.</p></Card>
        )}
        {status === "loading" ? (
          <EmptyState icon={Video}>Lecture de la santé des caméras…</EmptyState>
        ) : cameras.length === 0 ? (
          <EmptyState icon={Video}>Aucune caméra traitée. Configurez une caméra (1re zone) : elle apparaîtra ici automatiquement.</EmptyState>
        ) : (
          <div className="space-y-7">
            {sites.map((s) => {
              const onlineN = s.cameras.filter((c) => c.state === "online").length;
              return (
                <div key={s.id}>
                  <div className="flex items-center gap-3 mb-3">
                    <h2 className="text-[13px] font-semibold uppercase tracking-wide text-os-t2">{s.name}</h2>
                    <span className="os-num text-[12px] text-os-t4">{onlineN}/{s.cameras.length} en ligne</span>
                    <div className="flex-1 h-px bg-os-border" />
                  </div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {s.cameras.map(renderCard)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </OsShell>
  );
}

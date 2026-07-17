"use client";

/**
 * AlertNotifier — notification globale (toast + son) à la détection d'une
 * PERSONNE blacklistée ou d'une PLAQUE blacklistée.
 *
 * Source des signaux : flux Socket.IO 'metadata' du Core (le même que l'overlay
 * live), donc AUCUNE modification backend/Core requise :
 *   • plaque blacklistée → détection { type:'plate', alert:true }
 *   • personne blacklistée → détection { type:'face', recognized:true }
 *     (dans cette app, la « blacklist » = la liste des personnes enrôlées
 *      /api/people ; une reconnaissance faciale = un membre de cette liste).
 *
 * Le Core n'abonne qu'UNE caméra par socket → on ouvre un socket léger
 * (métadonnées seules, pas de vidéo) par caméra ACTIVE, découvertes via
 * l'événement 'cameras_list' (qui ne liste que les caméras actives → borné).
 *
 * Auto-contenu : aucune dépendance nouvelle (socket.io-client déjà présent, son
 * synthétisé via Web Audio API → pas de fichier audio à embarquer).
 */

import { useState, useEffect, useRef, useCallback } from "react";
import io from "socket.io-client";
import { SOCKET_URL } from "../../lib/publicUrls";
const COOLDOWN_MS = 20000;   // anti-spam : même piste re-alertée au plus toutes les 20 s
const MAX_TOASTS = 4;
const TOAST_TTL = 9000;
const MUTE_KEY = "osirion-alert-muted";

// ── Icônes SVG inline (auto-contenues, pas de lucide) ───────────────────────
const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IconUser = ({ className }) => (<Svg className={className}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>);
const IconCar = ({ className }) => (<Svg className={className}><path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" /><rect x="3" y="11" width="18" height="6" rx="2" /><circle cx="7.5" cy="17.5" r="1.5" /><circle cx="16.5" cy="17.5" r="1.5" /></Svg>);
const IconX = ({ className }) => (<Svg className={className}><path d="M18 6 6 18M6 6l12 12" /></Svg>);
const IconBellOn = ({ className }) => (<Svg className={className}><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></Svg>);
const IconBellOff = ({ className }) => (<Svg className={className}><path d="M13.7 21a2 2 0 0 1-3.4 0" /><path d="M18 8a6 6 0 0 0-9.3-5" /><path d="M6 8c0 7-3 9-3 9h13" /><path d="m2 2 20 20" /></Svg>);

// ── Son d'alerte synthétisé (double bip urgent), via Web Audio API ──────────
function playAlertSound(ctx) {
  const t0 = ctx.currentTime;
  const beep = (freq, start, dur) => {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "square";
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t0 + start);
    g.gain.exponentialRampToValueAtTime(0.22, t0 + start + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + start + dur);
    o.connect(g);
    g.connect(ctx.destination);
    o.start(t0 + start);
    o.stop(t0 + start + dur + 0.03);
  };
  beep(880, 0, 0.18);
  beep(660, 0.2, 0.24);
}

export default function AlertNotifier() {
  const [alerts, setAlerts] = useState([]);
  const [muted, setMuted] = useState(false);

  const mutedRef = useRef(false);
  const audioCtxRef = useRef(null);
  const cameraNamesRef = useRef(new Map());
  const cooldownRef = useRef(new Map());
  const timersRef = useRef([]);

  // Charger la préférence « muet » (persistée localement).
  useEffect(() => {
    try {
      const m = localStorage.getItem(MUTE_KEY) === "1";
      setMuted(m);
      mutedRef.current = m;
    } catch { /* localStorage indispo : ignore */ }
  }, []);

  useEffect(() => { mutedRef.current = muted; }, [muted]);

  const getAudioCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      const AC = typeof window !== "undefined" && (window.AudioContext || window.webkitAudioContext);
      if (AC) audioCtxRef.current = new AC();
    }
    return audioCtxRef.current;
  }, []);

  // Débloquer l'audio au 1er geste utilisateur (politique autoplay navigateur).
  useEffect(() => {
    const unlock = () => {
      const c = getAudioCtx();
      if (c && c.state === "suspended") c.resume().catch(() => {});
    };
    window.addEventListener("click", unlock);
    window.addEventListener("keydown", unlock);
    return () => {
      window.removeEventListener("click", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, [getAudioCtx]);

  const playSound = useCallback(() => {
    if (mutedRef.current) return;
    const c = getAudioCtx();
    if (!c) return;
    try {
      if (c.state === "suspended") c.resume().then(() => playAlertSound(c)).catch(() => {});
      else playAlertSound(c);
    } catch { /* lecture audio impossible : silencieux */ }
  }, [getAudioCtx]);

  const dismiss = useCallback((id) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const addAlert = useCallback((info) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setAlerts((prev) => [{ id, time: new Date(), ...info }, ...prev].slice(0, MAX_TOASTS));
    playSound();
    const t = setTimeout(() => {
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    }, TOAST_TTL);
    timersRef.current.push(t);
  }, [playSound]);

  const handleMeta = useCallback((data) => {
    if (!data || !Array.isArray(data.detections)) return;
    const now = Date.now();
    // Purge opportuniste du cache anti-spam.
    if (cooldownRef.current.size > 256) {
      for (const [k, ts] of cooldownRef.current) {
        if (now - ts > COOLDOWN_MS) cooldownRef.current.delete(k);
      }
    }
    for (const det of data.detections) {
      // On n'alerte QUE sur det.alert === true (vraie blacklist) : plaque
      // blacklistée OU personne sur liste de surveillance (is_blacklisted).
      // Une personne simplement reconnue (non blacklistée) ne déclenche RIEN.
      if (!det.alert) continue;
      const isPlate = det.type === "plate";

      const key = `${data.camera_id}|${det.type}|${det.track_id}`;
      const last = cooldownRef.current.get(key) || 0;
      if (now - last < COOLDOWN_MS) continue;
      cooldownRef.current.set(key, now);

      addAlert({
        kind: isPlate ? "plate" : "person",
        label: (det.label || "")
          .replace(/^⚠\s*/, "")
          .replace(/\s*\[BLACKLIST\]\s*$/i, "")
          .trim()
          || (isPlate ? "Plaque inconnue" : "Personne"),
        cameraName: cameraNamesRef.current.get(data.camera_id) || `Caméra ${data.camera_id}`,
      });
    }
  }, [addAlert]);

  // ── Connexions Socket.IO : 1 socket bootstrap (liste caméras) + 1 watcher
  //    léger par caméra active. ──────────────────────────────────────────────
  useEffect(() => {
    const watchers = new Map();           // camera_id -> socket
    const boot = io(SOCKET_URL, { withCredentials: true });

    boot.on("cameras_list", ({ cameras }) => {
      for (const cam of cameras || []) {
        cameraNamesRef.current.set(cam.id, cam.name);
        if (watchers.has(cam.id)) continue;
        const s = io(SOCKET_URL, { withCredentials: true });
        s.on("connect", () => s.emit("start_stream", { camera_id: cam.id }));
        s.on("metadata", handleMeta);
        watchers.set(cam.id, s);
      }
    });

    const timers = timersRef.current;
    return () => {
      try { boot.disconnect(); } catch { /* */ }
      for (const s of watchers.values()) {
        try { s.emit("stop_stream"); s.disconnect(); } catch { /* */ }
      }
      timers.forEach((t) => clearTimeout(t));
    };
  }, [handleMeta]);

  const toggleMute = () => {
    setMuted((m) => {
      const next = !m;
      try { localStorage.setItem(MUTE_KEY, next ? "1" : "0"); } catch { /* */ }
      return next;
    });
  };

  return (
    <>
      {/* Pile de toasts (au-dessus du contenu, sous d'éventuelles modales) */}
      <div className="fixed top-4 right-4 z-[60] flex flex-col gap-3 w-[330px] max-w-[calc(100vw-2rem)] pointer-events-none">
        {alerts.map((a) => (
          <div
            key={a.id}
            className="pointer-events-auto overflow-hidden rounded-2xl border border-rose-300/60 dark:border-rose-700/50 bg-white dark:bg-gray-900 shadow-2xl shadow-rose-900/20 animate-fade-in"
            role="alert"
          >
            <div className="h-1 w-full bg-gradient-to-r from-rose-600 to-red-500" />
            <div className="flex items-start gap-3 p-4">
              <div className="shrink-0 h-10 w-10 rounded-xl bg-rose-100 dark:bg-rose-900/40 text-rose-600 dark:text-rose-300 flex items-center justify-center">
                {a.kind === "plate" ? <IconCar className="h-5 w-5" /> : <IconUser className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
                  <p className="text-sm font-bold text-rose-700 dark:text-rose-300 truncate">
                    {a.kind === "plate" ? "Plaque blacklistée détectée" : "Personne blacklistée détectée"}
                  </p>
                </div>
                <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-white truncate">{a.label}</p>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">
                  {a.cameraName} · {a.time.toLocaleTimeString("fr-FR")}
                </p>
              </div>
              <button
                onClick={() => dismiss(a.id)}
                className="shrink-0 p-1 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                aria-label="Fermer"
              >
                <IconX className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Bouton son on/off (discret, en bas à droite) */}
      <button
        onClick={toggleMute}
        title={muted ? "Activer le son des alertes" : "Couper le son des alertes"}
        className="fixed bottom-4 right-4 z-[55] h-11 w-11 rounded-full border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        aria-label={muted ? "Activer le son des alertes" : "Couper le son des alertes"}
      >
        {muted ? <IconBellOff className="h-5 w-5 text-rose-500" /> : <IconBellOn className="h-5 w-5" />}
      </button>
    </>
  );
}

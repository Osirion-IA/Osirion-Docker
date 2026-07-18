"use client";

/**
 * AlertNotifier — notification globale (toast + son) à la détection d'une
 * PERSONNE blacklistée.
 *
 * Source des signaux : flux Socket.IO 'metadata' du Core (le même que l'overlay
 * live), donc AUCUNE modification backend/Core requise :
 *   • personne blacklistée → détection { type:'face', alert:true }
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
import { fetchWithRefresh } from "../../lib/fetchWithRefresh";
const MAX_TOASTS = 4;
const TOAST_TTL = 9000;
const MUTE_KEY = "osirion-alert-muted";

// ── Icônes SVG inline (auto-contenues, pas de lucide) ───────────────────────
const Svg = ({ className, children }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IconUser = ({ className }) => (<Svg className={className}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></Svg>);
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
  const timersRef = useRef([]);
  const seenRef = useRef(new Set());   // ids d'alertes déjà affichées (anti-doublon)

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

  // Récupère périodiquement les nouvelles alertes du backend (créées par le moteur
  // de règles) et les affiche en toast. Anti-doublon via seenRef ; le 1er passage
  // marque l'existant comme « vu » (pas de rafale de toasts au chargement).
  useEffect(() => {
    let active = true;
    let first = true;
    const timers = timersRef.current;
    const poll = async () => {
      try {
        const res = await fetchWithRefresh("/api/alerts?status=new");
        if (!active || !res?.ok) return;
        const data = await res.json();
        const list = Array.isArray(data) ? data : (data.alerts || []);
        for (const a of list) {
          if (a.id == null || seenRef.current.has(a.id)) continue;
          seenRef.current.add(a.id);
          if (!first) {
            addAlert({
              kind: a.kind,
              label: a.label || a.kind,
              cameraName: a.camera_name || (a.camera_id ? `Caméra ${a.camera_id}` : ""),
            });
          }
        }
        first = false;
      } catch { /* backend injoignable : réessai au prochain tick */ }
    };
    poll();
    const id = setInterval(poll, 10000);
    return () => {
      active = false;
      clearInterval(id);
      timers.forEach((t) => clearTimeout(t));
    };
  }, [addAlert]);

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
                <IconUser className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
                  <p className="text-sm font-bold text-rose-700 dark:text-rose-300 truncate">
                    {a.kind === "intrusion" ? "Intrusion détectée"
                      : a.kind === "crowd" ? "Attroupement détecté"
                      : a.kind === "queue" ? "File saturée"
                      : "Alerte déclenchée"}
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

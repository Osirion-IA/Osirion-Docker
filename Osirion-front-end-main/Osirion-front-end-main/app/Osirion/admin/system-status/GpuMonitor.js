"use client";

import { useState, useEffect, useRef } from "react";

// Le GPU est sur le Core (moteur de surveillance). On interroge son endpoint
// /api/gpu (CORS activé) directement depuis le navigateur, comme le toggle LPR.
const CORE_URL = process.env.NEXT_PUBLIC_CORE_URL || "http://localhost:5000";
const MAX_POINTS = 30;   // ~1 min d'historique à 2 s/échantillon
const POLL_MS = 2000;

function utilColor(v) {
  if (v >= 80) return "#ef4444";
  if (v >= 50) return "#f59e0b";
  return "#10b981";
}

// Sparkline SVG (aire + ligne), étirée en largeur. Données : utilisation % (0-100).
function Sparkline({ data, height = 72, color }) {
  if (!data || data.length === 0) return <div style={{ height }} />;
  const w = 100, h = 100;
  const n = data.length;
  const step = n > 1 ? w / (n - 1) : w;
  const pts = data.map((v, i) => {
    const y = h - (Math.max(0, Math.min(100, v)) / 100) * h;
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

export default function GpuMonitor() {
  const [status, setStatus] = useState("loading"); // loading | ok | unavailable | error
  const [gpus, setGpus] = useState([]);
  const histRef = useRef({});  // index -> [utilisation, ...]

  useEffect(() => {
    let active = true;
    let timer = null;

    const poll = async () => {
      try {
        const res = await fetch(`${CORE_URL}/api/gpu`, { cache: "no-store" });
        if (!active) return;
        if (!res.ok) { setStatus("error"); return; }
        const data = await res.json();
        if (!active) return;
        if (!data.available) {
          setStatus("unavailable");
          setGpus([]);
        } else {
          for (const g of data.gpus) {
            const arr = histRef.current[g.index] || [];
            arr.push(g.utilization_percent);
            if (arr.length > MAX_POINTS) arr.shift();
            histRef.current[g.index] = arr;
          }
          setGpus(data.gpus);
          setStatus("ok");
        }
      } catch {
        if (active) setStatus("error");
      } finally {
        if (active) timer = setTimeout(poll, POLL_MS);
      }
    };

    poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, []);

  return (
    <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-xl font-bold">GPU</h2>
        {status === "ok" && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">
            NVIDIA · live
          </span>
        )}
      </div>

      {status === "loading" && (
        <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">Lecture des métriques GPU…</div>
      )}
      {status === "unavailable" && (
        <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
          Aucun GPU NVIDIA détecté (le Core tourne en mode CPU).
        </div>
      )}
      {status === "error" && (
        <div className="py-8 text-center text-sm text-amber-600 dark:text-amber-400">
          Métriques GPU indisponibles — Core injoignable sur {CORE_URL}.
        </div>
      )}

      {status === "ok" && (
        <div className="space-y-6">
          {gpus.map((g) => {
            const hist = histRef.current[g.index] || [];
            const color = utilColor(g.utilization_percent);
            return (
              <div key={g.index}>
                <div className="flex items-center justify-between mb-1">
                  <div className="min-w-0">
                    <div className="font-semibold text-gray-900 dark:text-white truncate">
                      GPU {g.index} · {g.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {g.memory_used_mb.toFixed(0)} / {g.memory_total_mb.toFixed(0)} Mo · {g.temperature_c.toFixed(0)}°C
                    </div>
                  </div>
                  <div className="text-2xl font-bold tabular-nums" style={{ color }}>
                    {g.utilization_percent.toFixed(0)}%
                  </div>
                </div>

                <Sparkline data={hist} color={color} />

                {/* Barre mémoire */}
                <div className="mt-2">
                  <div className="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-1">
                    <span>Mémoire</span>
                    <span>{g.memory_percent}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                    <div className="h-2 rounded-full bg-indigo-500" style={{ width: `${Math.min(100, g.memory_percent)}%` }} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

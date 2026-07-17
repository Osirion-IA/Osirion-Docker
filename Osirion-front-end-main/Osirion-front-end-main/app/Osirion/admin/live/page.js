"use client";

import { useState, useEffect, useRef } from "react";
import io from "socket.io-client";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import CameraStream from "./CameraStream";
import { SOCKET_URL } from "../../../lib/publicUrls";

export default function LiveStreamingPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [gridSize, setGridSize] = useState(3);
  const [cameras, setCameras] = useState([]);
  const [liveLatency, setLiveLatency] = useState(0);
  const user = useAuth();
  const currentRole = user?.role || "viewer";

  useEffect(() => {
    const socket = io(SOCKET_URL, { withCredentials: true });
    socket.on("cameras_list", (data) => {
      if (data?.cameras) setCameras(data.cameras);
    });
    return () => socket.disconnect();
  }, []);

  const latencyColor =
    liveLatency === 0 ? "text-gray-400 dark:text-gray-500" :
    liveLatency < 100 ? "text-emerald-600 dark:text-emerald-400" :
    liveLatency < 250 ? "text-yellow-600 dark:text-yellow-400" :
    "text-red-600 dark:text-red-400";

  const gridCols = {
    2: "grid-cols-1 sm:grid-cols-2",
    3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
    4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
  };

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((p) => !p)}
          currentPath="/Osirion/admin/live"
        />

        <main className={`flex-1 transition-all duration-300 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Live Streaming"
            subtitle={`${cameras.length} caméra${cameras.length !== 1 ? "s" : ""} en direct`}
            showSearch={false}
            actions={
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 text-sm">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-medium">{cameras.length} en direct</span>
              </div>
            }
          />

          {selectedCamera ? (
            /* ── Vue plein écran ──────────────────────────────────────────── */
            <div className="px-4 lg:px-8 py-5">
              {/* Bouton retour */}
              <button
                onClick={() => { setSelectedCamera(null); setLiveLatency(0); }}
                className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
                Retour à la mosaïque
              </button>

              <div className="flex flex-col xl:flex-row gap-5">
                {/* Colonne principale */}
                <div className="flex-1 min-w-0 space-y-4">
                  {/* Lecteur vidéo */}
                  <div className="relative rounded-2xl overflow-hidden shadow-2xl bg-gray-950 aspect-[4/3]">
                    <CameraStream
                      cameraId={selectedCamera.id}
                      onLatencyUpdate={setLiveLatency}
                      showStats={false}
                    />

                    {/* Badge LIVE */}
                    <div className="absolute top-4 left-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-bold shadow-lg z-10">
                      <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
                      LIVE
                    </div>

                    {/* Overlay nom + localisation */}
                    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/75 to-transparent px-5 py-4 z-10">
                      <h3 className="text-white font-semibold text-base leading-tight">
                        {selectedCamera.name}
                      </h3>
                      <p className="text-white/60 text-sm mt-0.5">{selectedCamera.location}</p>
                    </div>
                  </div>

                  {/* Barre de statut live */}
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800">
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                      En direct
                    </div>
                    <div className="h-4 w-px bg-gray-200 dark:bg-gray-700" />
                    <span className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                      640 × 480
                    </span>
                    <div className="h-4 w-px bg-gray-200 dark:bg-gray-700" />
                    <span className={`text-sm font-mono font-semibold ${latencyColor}`}>
                      {liveLatency > 0 ? `${liveLatency} ms` : "—"}
                    </span>
                    <div className="flex-1" />
                    <span className="text-xs text-gray-400 dark:text-gray-600 font-mono">
                      cam #{selectedCamera.id}
                    </span>
                  </div>
                </div>

                {/* Panneau latéral */}
                <div className="xl:w-72 space-y-4 flex-shrink-0">
                  {/* Métriques */}
                  <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
                      <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                        Métriques
                      </h3>
                    </div>
                    <div className="divide-y divide-gray-100 dark:divide-gray-800">
                      {[
                        { label: "Résolution", value: "640 × 480" },
                        { label: "Codec source", value: "H.264" },
                        {
                          label: "Latence",
                          value: liveLatency > 0 ? `${liveLatency} ms` : "—",
                          className: latencyColor,
                        },
                        { label: "Caméra ID", value: `#${selectedCamera.id}` },
                      ].map(({ label, value, className }) => (
                        <div key={label} className="flex items-center justify-between px-4 py-3">
                          <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
                          <span className={`text-sm font-semibold font-mono text-gray-900 dark:text-white ${className ?? ""}`}>
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Autres caméras */}
                  {cameras.filter((c) => c.id !== selectedCamera.id).length > 0 && (
                    <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-100 dark:border-gray-800 overflow-hidden">
                      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
                        <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                          Autres caméras
                        </h3>
                      </div>
                      <div className="max-h-[50vh] overflow-y-auto">
                        {cameras
                          .filter((c) => c.id !== selectedCamera.id)
                          .map((camera) => (
                            <button
                              key={camera.id}
                              onClick={() => { setSelectedCamera(camera); setLiveLatency(0); }}
                              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left border-b border-gray-50 dark:border-gray-800/50 last:border-0"
                            >
                              {/* Miniature live */}
                              <div className="relative h-11 w-[58px] rounded-md overflow-hidden bg-gray-900 flex-shrink-0">
                                <CameraStream cameraId={camera.id} showStats={false} />
                                <div className="absolute top-0.5 left-0.5 flex items-center gap-0.5 px-1 py-0.5 rounded bg-red-600 text-white text-[9px] font-bold leading-none">
                                  <span className="h-1 w-1 rounded-full bg-white animate-pulse" />
                                  LIVE
                                </div>
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold text-gray-900 dark:text-white truncate">
                                  {camera.name}
                                </p>
                                <p className="text-[10px] text-gray-400 dark:text-gray-500 truncate mt-0.5">
                                  {camera.location}
                                </p>
                              </div>
                              <svg className="h-4 w-4 text-gray-300 dark:text-gray-600 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="m9 18 6-6-6-6" />
                              </svg>
                            </button>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* ── Vue grille mosaïque ────────────────────────────────────────── */
            <div className="px-4 lg:px-8 py-5">
              {/* Barre de contrôles */}
              <div className="mb-5 flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                    Disposition
                  </span>
                  <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                    {[2, 3, 4].map((size) => (
                      <button
                        key={size}
                        onClick={() => setGridSize(size)}
                        className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                          gridSize === size
                            ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                            : "text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-white"
                        }`}
                      >
                        {size}×{size}
                      </button>
                    ))}
                  </div>
                </div>

                {cameras.length === 0 && (
                  <span className="text-sm text-gray-400 dark:text-gray-500 italic">
                    Aucune caméra active
                  </span>
                )}
              </div>

              {/* Grille */}
              {cameras.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
                  <div className="h-16 w-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                    <svg className="h-8 w-8 text-gray-400 dark:text-gray-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect x="4" y="7" width="16" height="10" rx="1.5" />
                      <path d="m8 7 2-3h4l2 3" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                      Aucune caméra connectée
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">
                      Vérifiez que le service core est actif et que des caméras sont configurées.
                    </p>
                  </div>
                </div>
              ) : (
                <div className={`grid gap-3 ${gridCols[gridSize]}`}>
                  {cameras.map((camera) => (
                    <button
                      key={camera.id}
                      onClick={() => setSelectedCamera(camera)}
                      className="group relative rounded-xl overflow-hidden bg-gray-950 aspect-[4/3] ring-1 ring-gray-800 hover:ring-2 hover:ring-blue-500 transition-all duration-200 hover:scale-[1.015] focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {/* Flux live en fond */}
                      <CameraStream cameraId={camera.id} showStats={false} />

                      {/* Badge LIVE */}
                      <div className="absolute top-2.5 left-2.5 z-10 flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-600 text-white text-[10px] font-bold shadow">
                        <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
                        LIVE
                      </div>

                      {/* Overlay info bas */}
                      <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-black/80 via-black/30 to-transparent px-3 py-2.5">
                        <p className="text-white text-xs font-semibold truncate">{camera.name}</p>
                        <p className="text-white/55 text-[10px] truncate mt-0.5">{camera.location}</p>
                      </div>

                      {/* Hover : icône agrandir */}
                      <div className="absolute inset-0 z-10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/60 backdrop-blur-sm text-white text-xs font-medium">
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M15 3h6m0 0v6m0-6-7 7M9 21H3m0 0v-6m0 6 7-7" />
                          </svg>
                          Agrandir
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

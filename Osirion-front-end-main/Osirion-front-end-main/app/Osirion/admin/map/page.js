"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import "leaflet/dist/leaflet.css";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";

// Carte géospatiale (OpenStreetMap / Leaflet) des caméras.
// Consomme le proxy /api/cameras/map-data (caméras actives + géolocalisées).
// Leaflet est BUNDLÉ (dépendance npm), fonctionne hors-ligne. On utilise des
// circleMarker (vectoriels) → pas de problème d'icônes-images manquantes.

// Charge Leaflet UNE fois, côté client uniquement : import dynamique pour éviter
// l'évaluation au rendu serveur (Leaflet référence `window` dès l'import). Le
// module résolu est mémorisé sur window.L pour le reste du composant.
let _leafletPromise = null;
function loadLeaflet() {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve(window.L);
  if (!_leafletPromise) {
    _leafletPromise = import("leaflet").then((mod) => {
      const L = mod.default || mod;
      window.L = L;
      return L;
    });
  }
  return _leafletPromise;
}

// Couleur selon les modules effectivement actifs sur la caméra.
function moduleColor(modules = []) {
  const f = modules.includes("facial");
  const l = modules.includes("lpr");
  if (f && l) return "#7c3aed"; // violet — les deux
  if (f) return "#2563eb"; // bleu — facial
  if (l) return "#d97706"; // ambre — LPR
  return "#6b7280"; // gris — aucun
}

// Point destination (approx. équirectangulaire, valable à quelques dizaines de m).
// bearing en degrés depuis le nord, sens horaire.
function destPoint(lat, lng, distanceM, bearingDeg) {
  const R = 6378137;
  const br = (bearingDeg * Math.PI) / 180;
  const latR = (lat * Math.PI) / 180;
  const dLat = (distanceM * Math.cos(br)) / R;
  const dLng = (distanceM * Math.sin(br)) / (R * Math.cos(latR));
  return [lat + (dLat * 180) / Math.PI, lng + (dLng * 180) / Math.PI];
}

// Polygone en secteur (cône de champ de vision) autour d'un cap.
function fovCone(lat, lng, bearingDeg, { radius = 70, half = 28, steps = 10 } = {}) {
  const pts = [[lat, lng]];
  for (let i = 0; i <= steps; i++) {
    const a = bearingDeg - half + (2 * half * i) / steps;
    pts.push(destPoint(lat, lng, radius, a));
  }
  return pts;
}

export default function MapPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [cams, setCams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/cameras/map-data");
      if (!res.ok) throw new Error("map-data");
      setCams((await res.json()) || []);
    } catch {
      setError("Erreur lors du chargement des données carte.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Init Leaflet + première charge des données.
  useEffect(() => {
    let cancelled = false;
    loadLeaflet()
      .then((L) => {
        if (cancelled || !containerRef.current || mapRef.current) return;
        const map = L.map(containerRef.current, { scrollWheelZoom: true }).setView([14.6928, -17.4467], 12); // Dakar par défaut
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(map);
        layerRef.current = L.layerGroup().addTo(map);
        mapRef.current = map;
        setReady(true);
        setTimeout(() => map.invalidateSize(), 100);
      })
      .catch((e) => setError(e.message || "Échec du chargement de la carte."));

    fetchData();
    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        layerRef.current = null;
      }
    };
  }, [fetchData]);

  // Re-dessine les marqueurs + cônes quand les données ou la carte changent.
  useEffect(() => {
    const L = typeof window !== "undefined" ? window.L : null;
    if (!ready || !L || !mapRef.current || !layerRef.current) return;

    layerRef.current.clearLayers();
    const bounds = [];
    for (const c of cams) {
      if (c.latitude == null || c.longitude == null) continue;
      const color = moduleColor(c.active_modules);
      const center = [c.latitude, c.longitude];
      bounds.push(center);

      // Cône de champ de vision.
      L.polygon(fovCone(c.latitude, c.longitude, c.bearing || 0), {
        color,
        weight: 1,
        fillColor: color,
        fillOpacity: 0.18,
      }).addTo(layerRef.current);

      // Marqueur.
      const modulesTxt = (c.active_modules || []).length
        ? (c.active_modules || []).join(", ")
        : "aucun module actif";
      L.circleMarker(center, {
        radius: 7,
        color: "#ffffff",
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      })
        .bindPopup(
          `<div style="font-size:13px"><strong>${c.name}</strong><br/>` +
            `cap : ${Math.round(c.bearing || 0)}°<br/>` +
            `modules : ${modulesTxt}</div>`
        )
        .addTo(layerRef.current);
    }

    if (bounds.length > 0) {
      mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
    }
  }, [cams, ready]);

  const geolocated = cams.length;

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((p) => !p)}
          currentPath="/Osirion/admin/map"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Carte des caméras"
            subtitle={`${geolocated} caméra(s) active(s) géolocalisée(s) • OpenStreetMap`}
            showSearch={false}
            actions={
              <button onClick={fetchData} className="px-4 py-2.5 rounded-xl bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 text-sm font-medium transition-colors inline-flex items-center gap-2">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
                Actualiser
              </button>
            }
          />

          <div className="px-6 lg:px-10 py-6">
            {error && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
                {error}
              </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
              {/* Carte */}
              <div className="xl:col-span-3 relative rounded-2xl overflow-hidden border border-gray-200 dark:border-gray-800 shadow-sm">
                <div ref={containerRef} style={{ height: "72vh", width: "100%" }} className="bg-gray-100 dark:bg-gray-800" />
                {(!ready || loading) && (
                  <div className="absolute inset-0 flex items-center justify-center bg-white/40 dark:bg-gray-900/40 backdrop-blur-sm pointer-events-none">
                    <span className="text-sm text-gray-600 dark:text-gray-300">Chargement de la carte…</span>
                  </div>
                )}
              </div>

              {/* Panneau latéral : légende + liste */}
              <div className="space-y-4">
                <div className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Légende</h3>
                  <ul className="space-y-2 text-sm">
                    <LegendRow color="#2563eb" label="Facial" />
                    <LegendRow color="#d97706" label="LPR / Plaques" />
                    <LegendRow color="#7c3aed" label="Facial + LPR" />
                    <LegendRow color="#6b7280" label="Aucun module actif" />
                  </ul>
                  <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                    Le cône indique le champ de vision (cap de l'objectif).
                  </p>
                </div>

                <div className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Caméras ({geolocated})</h3>
                  {geolocated === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Aucune caméra active géolocalisée. Renseignez latitude / longitude / cap sur les caméras.
                    </p>
                  ) : (
                    <ul className="space-y-1.5 max-h-[46vh] overflow-y-auto">
                      {cams.map((c) => (
                        <li key={c.id} className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/50">
                          <span className="shrink-0 h-2.5 w-2.5 rounded-full" style={{ backgroundColor: moduleColor(c.active_modules) }} />
                          <div className="min-w-0">
                            <p className="text-sm text-gray-900 dark:text-white truncate">{c.name}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                              {(c.active_modules || []).join(", ") || "aucun module"} • {Math.round(c.bearing || 0)}°
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function LegendRow({ color, label }) {
  return (
    <li className="flex items-center gap-2.5">
      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-gray-700 dark:text-gray-300">{label}</span>
    </li>
  );
}

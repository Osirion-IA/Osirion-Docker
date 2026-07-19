"use client";

/**
 * Carte des caméras — section Configurer (thème clair). Carte géospatiale Leaflet
 * (OpenStreetMap) des caméras actives géolocalisées + cône de champ de vision.
 * Données /api/cameras/map-data. Leaflet bundlé (import dynamique côté client).
 */
import { useState, useEffect, useRef, useCallback } from "react";
import "leaflet/dist/leaflet.css";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, RefreshButton } from "../_osirion/ui";

const CAM_COLOR = "#2f7fd1"; // os-blue en hex (Leaflet ne lit pas les var CSS)

let _leafletPromise = null;
function loadLeaflet() {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve(window.L);
  if (!_leafletPromise) _leafletPromise = import("leaflet").then((mod) => { const L = mod.default || mod; window.L = L; return L; });
  return _leafletPromise;
}
function destPoint(lat, lng, distanceM, bearingDeg) {
  const R = 6378137, br = (bearingDeg * Math.PI) / 180, latR = (lat * Math.PI) / 180;
  const dLat = (distanceM * Math.cos(br)) / R, dLng = (distanceM * Math.sin(br)) / (R * Math.cos(latR));
  return [lat + (dLat * 180) / Math.PI, lng + (dLng * 180) / Math.PI];
}
function fovCone(lat, lng, bearingDeg, { radius = 70, half = 28, steps = 10 } = {}) {
  const pts = [[lat, lng]];
  for (let i = 0; i <= steps; i++) pts.push(destPoint(lat, lng, radius, bearingDeg - half + (2 * half * i) / steps));
  return pts;
}

export default function MapPage() {
  const [cams, setCams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const containerRef = useRef(null), mapRef = useRef(null), layerRef = useRef(null);

  const fetchData = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await fetch("/api/cameras/map-data");
      if (!res.ok) throw new Error("map-data");
      setCams((await res.json()) || []);
    } catch { setError("Erreur lors du chargement des données carte."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current, { scrollWheelZoom: true }).setView([14.6928, -17.4467], 12);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map; setReady(true);
      setTimeout(() => map.invalidateSize(), 100);
    }).catch((e) => setError(e.message || "Échec du chargement de la carte."));
    fetchData();
    return () => { cancelled = true; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; layerRef.current = null; } };
  }, [fetchData]);

  useEffect(() => {
    const L = typeof window !== "undefined" ? window.L : null;
    if (!ready || !L || !mapRef.current || !layerRef.current) return;
    layerRef.current.clearLayers();
    const bounds = [];
    for (const c of cams) {
      if (c.latitude == null || c.longitude == null) continue;
      const center = [c.latitude, c.longitude];
      bounds.push(center);
      L.polygon(fovCone(c.latitude, c.longitude, c.bearing || 0), { color: CAM_COLOR, weight: 1, fillColor: CAM_COLOR, fillOpacity: 0.18 }).addTo(layerRef.current);
      L.circleMarker(center, { radius: 7, color: "#ffffff", weight: 2, fillColor: CAM_COLOR, fillOpacity: 1 })
        .bindPopup(`<div style="font-size:13px"><strong>${c.name}</strong><br/>cap : ${Math.round(c.bearing || 0)}°</div>`)
        .addTo(layerRef.current);
    }
    if (bounds.length > 0) mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
  }, [cams, ready]);

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Carte des caméras"
          subtitle={`${cams.length} caméra(s) active(s) géolocalisée(s) · OpenStreetMap`}
          actions={<RefreshButton onClick={fetchData} spinning={loading} />}
        />
        {error && <Card className="p-3 mb-4"><p className="text-[13px] text-os-red">{error}</p></Card>}

        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          <div className="xl:col-span-3 relative rounded-os-lg overflow-hidden border border-os-border">
            <div ref={containerRef} style={{ height: "72vh", width: "100%" }} className="bg-os-card-2" />
            {(!ready || loading) && (
              <div className="absolute inset-0 grid place-items-center bg-black/10 backdrop-blur-sm pointer-events-none">
                <span className="text-[13px] text-os-t2">Chargement de la carte…</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <Card className="p-4">
              <h3 className="text-[14px] font-semibold text-os-t1 mb-3">Légende</h3>
              <div className="flex items-center gap-2.5 text-[13px]">
                <span className="h-3 w-3 rounded-full" style={{ background: CAM_COLOR }} /><span className="text-os-t2">Caméra active</span>
              </div>
              <p className="mt-3 text-[12px] text-os-t3">Le cône indique le champ de vision (cap de l&apos;objectif).</p>
            </Card>
            <Card className="p-4">
              <h3 className="text-[14px] font-semibold text-os-t1 mb-3">Caméras ({cams.length})</h3>
              {cams.length === 0 ? (
                <p className="text-[13px] text-os-t3">Aucune caméra active géolocalisée. Renseignez latitude / longitude / cap.</p>
              ) : (
                <ul className="space-y-1 max-h-[46vh] overflow-y-auto">
                  {cams.map((c) => (
                    <li key={c.id} className="flex items-center gap-2.5 px-2 py-2 rounded-os hover:bg-black/[0.03]">
                      <span className="shrink-0 h-2.5 w-2.5 rounded-full" style={{ background: CAM_COLOR }} />
                      <div className="min-w-0">
                        <p className="text-[13px] text-os-t1 truncate">{c.name}</p>
                        <p className="os-num text-[11px] text-os-t3 truncate">Cap {Math.round(c.bearing || 0)}°</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </div>
    </OsShell>
  );
}

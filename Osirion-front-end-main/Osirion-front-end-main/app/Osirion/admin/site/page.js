"use client";

/**
 * Caméras & site — section Configurer (thème clair). Synthèse du parc : table
 * (état, emplacement, géo) + plan du site schématique à pastilles d'état.
 * La gestion (ajout/édition/suppression) reste sur /Osirion/admin/cameras.
 * Données : /api/cameras (+ /api/cameras/map-data pour la géo).
 */
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { MapPin, Video } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card } from "../_osirion/ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

export default function SitePage() {
  const [cams, setCams] = useState([]);

  const load = useCallback(async () => {
    const r = await fetchWithRefresh("/api/cameras");
    const data = r?.ok ? await r.json() : [];
    setCams(Array.isArray(data) ? data : []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const online = cams.filter((c) => c.is_active).length;
  const geo = cams.filter((c) => c.latitude != null && c.longitude != null);

  // Normalisation lat/long → boîte 0..1 pour le plan schématique.
  const bounds = geo.reduce((b, c) => ({
    minLat: Math.min(b.minLat, c.latitude), maxLat: Math.max(b.maxLat, c.latitude),
    minLng: Math.min(b.minLng, c.longitude), maxLng: Math.max(b.maxLng, c.longitude),
  }), { minLat: Infinity, maxLat: -Infinity, minLng: Infinity, maxLng: -Infinity });
  const pos = (c) => {
    const spanLat = bounds.maxLat - bounds.minLat || 1;
    const spanLng = bounds.maxLng - bounds.minLng || 1;
    return {
      left: `${8 + ((c.longitude - bounds.minLng) / spanLng) * 84}%`,
      top: `${8 + (1 - (c.latitude - bounds.minLat) / spanLat) * 84}%`,
    };
  };

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Caméras & site"
          subtitle={`${online}/${cams.length} caméra(s) en ligne · ${geo.length} géolocalisée(s)`}
          actions={<Link href="/Osirion/admin/cameras" className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover">Gérer le parc</Link>}
        />

        <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_0.75fr] gap-4">
          <Card className="overflow-hidden">
            {cams.length === 0 ? (
              <div className="py-14 text-center"><Video className="h-9 w-9 mx-auto mb-3 text-os-t4" strokeWidth={1.6} /><p className="text-[13px] text-os-t3">Aucune caméra configurée.</p></div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-os-t3 border-b border-os-border">
                      <th className="px-4 py-3 font-semibold">État</th>
                      <th className="px-4 py-3 font-semibold">Caméra</th>
                      <th className="px-4 py-3 font-semibold">Emplacement</th>
                      <th className="px-4 py-3 font-semibold">Coordonnées</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cams.map((c) => (
                      <tr key={c.id} className="border-b border-os-border last:border-0">
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-1.5">
                            <span className={`h-2 w-2 rounded-full ${c.is_active ? "bg-os-green" : "bg-os-t4"}`} />
                            <span className="text-os-t2">{c.is_active ? "En ligne" : "Inactive"}</span>
                          </span>
                        </td>
                        <td className="px-4 py-3 text-os-t1 font-medium">{c.cam_name || `Caméra ${c.id}`}</td>
                        <td className="px-4 py-3 text-os-t2">{c.location || "—"}</td>
                        <td className="px-4 py-3 os-num text-os-t3">{c.latitude != null && c.longitude != null ? `${Number(c.latitude).toFixed(4)}, ${Number(c.longitude).toFixed(4)}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card className="p-5">
            <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Plan du site</h3>
            {geo.length === 0 ? (
              <div className="aspect-square rounded-os border border-dashed border-os-border-2 grid place-items-center text-center p-6">
                <p className="text-[12px] text-os-t3">Aucune caméra géolocalisée. Renseignez latitude/longitude dans la gestion du parc pour les placer sur le plan.</p>
              </div>
            ) : (
              <div className="relative aspect-square rounded-os bg-os-card-2 border border-os-border-2 overflow-hidden">
                <div className="absolute inset-0 opacity-[0.5]" style={{ backgroundImage: "linear-gradient(var(--os-border) 1px, transparent 1px), linear-gradient(90deg, var(--os-border) 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
                {geo.map((c) => (
                  <div key={c.id} className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center" style={pos(c)} title={c.cam_name}>
                    <span className={`h-3 w-3 rounded-full ring-4 ${c.is_active ? "bg-os-green ring-os-green/20" : "bg-os-t4 ring-os-t4/20"}`} />
                    <span className="mt-1 os-num text-[10px] text-os-t3 whitespace-nowrap max-w-[80px] truncate">{c.cam_name}</span>
                  </div>
                ))}
                <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 text-[11px] text-os-t4"><MapPin className="h-3 w-3" /> {geo.length} points</span>
              </div>
            )}
          </Card>
        </div>
      </div>
    </OsShell>
  );
}

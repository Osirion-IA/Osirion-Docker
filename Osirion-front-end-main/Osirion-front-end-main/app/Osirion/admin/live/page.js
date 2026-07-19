"use client";

/**
 * Mur de caméras — section Surveiller (thème sombre). Grille 2/3/4 de flux WebRTC
 * avec overlay de détection ANONYME (boîtes vertes, zones, compteurs) rendu par
 * CameraStream. 100 % anonyme. La liste des caméras ACTIVES vient du Core via
 * Socket.IO ('cameras_list') → on n'affiche que ce que le Core diffuse réellement.
 */
import { useState, useEffect } from "react";
import io from "socket.io-client";
import { Maximize2 } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { Segmented } from "../_osirion/ui";
import CameraStream from "./CameraStream";
import { SOCKET_URL } from "../../../lib/publicUrls";

const GRID = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};
const SIZES = [{ value: 2, label: "2" }, { value: 3, label: "3" }, { value: 4, label: "4" }];

export default function LiveWallPage() {
  const [cams, setCams] = useState([]);
  const [size, setSize] = useState(3);

  useEffect(() => {
    const socket = io(SOCKET_URL, { withCredentials: true });
    socket.on("cameras_list", (data) => { if (data?.cameras) setCams(data.cameras); });
    return () => socket.disconnect();
  }, []);

  return (
    <OsShell>
      <div className="p-6">
        <div className="flex items-end justify-between gap-4 mb-5">
          <div>
            <h1 className="text-[22px] font-bold text-os-t1">Mur de caméras</h1>
            <p className="text-[13px] text-os-t3 mt-0.5">Flux WebRTC · overlay de détection anonyme temps réel</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[12px] text-os-t3">Colonnes</span>
            <Segmented value={size} onChange={setSize} options={SIZES} size="sm" />
          </div>
        </div>

        {cams.length === 0 ? (
          <div className="rounded-os-lg border border-os-border bg-os-card py-20 text-center">
            <p className="text-[13px] text-os-t3">Aucune caméra active diffusée. Activez une caméra dans « Caméras &amp; site » et assurez-vous que le Core tourne.</p>
          </div>
        ) : (
          <div className={`grid gap-3 ${GRID[size]}`}>
            {cams.map((c) => (
              <div key={c.id} className="group relative rounded-os-lg overflow-hidden border border-os-border bg-[#0d0f12]">
                <div className="relative aspect-video">
                  <CameraStream cameraId={c.id} showStats={false} />
                </div>
                <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 to-transparent px-3 py-2.5 flex items-end justify-between pointer-events-none">
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold text-white truncate">{c.name || `Caméra ${c.id}`}</p>
                    {c.location && <p className="text-[11px] text-white/60 truncate">{c.location}</p>}
                  </div>
                  <Maximize2 className="h-4 w-4 text-white/50 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </OsShell>
  );
}

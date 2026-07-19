"use client";

/**
 * Zones & comptage — section Configurer (thème clair). Éditeur interactif :
 * clic sur l'image caméra pour poser les sommets d'un polygone (zone) ou 2 points
 * (ligne de comptage). Les zones comptent des PRÉSENCES ANONYMES dans un périmètre.
 * Sauvegarde via /api/zones et /api/zones/lines.
 */
import { useState, useEffect, useCallback } from "react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import CameraStream from "../live/CameraStream";

const ZONE_KINDS = [
  { value: "occupancy", label: "Occupation", color: "#2f7fd1" },
  { value: "queue", label: "File d'attente", color: "#f5a623" },
  { value: "crowd", label: "Attroupement", color: "#e60027" },
  { value: "generic", label: "Générique", color: "#1faa59" },
];
const kindColor = (k) => (ZONE_KINDS.find((z) => z.value === k)?.color || "#1faa59");
const kindLabel = (k) => (ZONE_KINDS.find((z) => z.value === k)?.label || k);
const LINE_COLOR = "#f5a623";

export default function ZonesPage() {
  const user = useAuth();
  const canWrite = ["admin", "user"].includes(user?.role);

  const [cameras, setCameras] = useState([]);
  const [camId, setCamId] = useState(null);
  const [zones, setZones] = useState([]);
  const [lines, setLines] = useState([]);
  const [tool, setTool] = useState("select"); // "select" | "zone" | "line"
  const [draft, setDraft] = useState([]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("occupancy");
  const [threshold, setThreshold] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      const r = await fetchWithRefresh("/api/cameras");
      if (r?.ok) {
        const cams = await r.json();
        const list = Array.isArray(cams) ? cams : [];
        setCameras(list);
        setCamId((prev) => (prev == null && list.length ? list[0].id : prev));
      }
    })();
  }, []);

  const loadShapes = useCallback(async (id) => {
    if (id == null) return;
    const [zr, lr] = await Promise.all([
      fetchWithRefresh(`/api/zones?camera_id=${id}`),
      fetchWithRefresh(`/api/zones/lines?camera_id=${id}`),
    ]);
    setZones(zr?.ok ? await zr.json() : []);
    setLines(lr?.ok ? await lr.json() : []);
  }, []);

  useEffect(() => { setDraft([]); setTool("select"); setMsg(""); loadShapes(camId); }, [camId, loadShapes]);

  const onSvgClick = (e) => {
    if (!canWrite || tool === "select") return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    const pt = [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
    setDraft((d) => (tool === "line" ? [...d, pt].slice(-2) : [...d, pt]));
  };
  const cancelDraft = () => { setDraft([]); setName(""); setThreshold(""); setMsg(""); setTool("select"); };
  const undoPoint = () => setDraft((d) => d.slice(0, -1));

  const save = async () => {
    setMsg("");
    if (!name.trim()) { setMsg("Le nom est requis."); return; }
    try {
      if (tool === "zone") {
        if (draft.length < 3) { setMsg("Un polygone exige au moins 3 points."); return; }
        const r = await fetchWithRefresh("/api/zones", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: camId, name: name.trim(), kind, polygon: draft, color: kindColor(kind), threshold: threshold ? Number(threshold) : null }),
        });
        if (!r?.ok) { setMsg("Échec de l'enregistrement de la zone."); return; }
      } else if (tool === "line") {
        if (draft.length < 2) { setMsg("Une ligne exige exactement 2 points."); return; }
        const r = await fetchWithRefresh("/api/zones/lines", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: camId, name: name.trim(), point_a: draft[0], point_b: draft[1] }),
        });
        if (!r?.ok) { setMsg("Échec de l'enregistrement de la ligne."); return; }
      }
      cancelDraft(); loadShapes(camId);
    } catch { setMsg("Erreur réseau."); }
  };
  const delZone = async (id) => { await fetchWithRefresh(`/api/zones/${id}`, { method: "DELETE" }); loadShapes(camId); };
  const delLine = async (id) => { await fetchWithRefresh(`/api/zones/lines/${id}`, { method: "DELETE" }); loadShapes(camId); };

  const ptStr = (pts) => pts.map((p) => `${p[0]},${p[1]}`).join(" ");
  const toolBtn = (active, activeColor) =>
    `px-3.5 py-2 rounded-os text-[13px] font-medium border ${active ? `${activeColor} text-white border-transparent` : "border-os-border text-os-t2 hover:text-os-t1"}`;

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Zones & comptage"
          subtitle="Dessinez zones et lignes de comptage directement sur l'image de la caméra"
          actions={
            <select value={camId ?? ""} onChange={(e) => setCamId(Number(e.target.value))}
              className="rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none">
              {cameras.length === 0 && <option value="">Aucune caméra</option>}
              {cameras.map((c) => <option key={c.id} value={c.id}>Caméra · {c.cam_name || c.id}</option>)}
            </select>
          }
        />

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <div className="xl:col-span-2">
            <Card className="p-4">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <button onClick={() => { setTool("zone"); setDraft([]); setMsg(""); }} disabled={!canWrite} className={toolBtn(tool === "zone", "bg-os-cta")}>Zone</button>
                <button onClick={() => { setTool("line"); setDraft([]); setMsg(""); }} disabled={!canWrite} className={toolBtn(tool === "line", "bg-os-amber")}>Ligne de comptage</button>
                <button onClick={cancelDraft} className={toolBtn(tool === "select", "bg-os-cta")}>Sélection</button>
                <button onClick={cancelDraft} className="ml-auto px-3.5 py-2 rounded-os text-[13px] text-os-t3 hover:text-os-t1 border border-os-border">Effacer</button>
              </div>

              <div className="relative w-full aspect-video bg-[#0d0f12] rounded-os overflow-hidden border border-os-border-2">
                {camId != null && <CameraStream cameraId={camId} showStats={false} />}
                {tool !== "select" && draft.length === 0 && (
                  <div className="absolute inset-0 grid place-items-center pointer-events-none">
                    <span className="os-num text-[12px] text-white/80 bg-black/50 px-3 py-1.5 rounded-os">Cliquez pour poser les sommets de la {tool === "line" ? "ligne" : "zone"}</span>
                  </div>
                )}
                <svg viewBox="0 0 1 1" preserveAspectRatio="none" onClick={onSvgClick}
                  className={`absolute inset-0 w-full h-full ${tool !== "select" ? "cursor-crosshair" : ""}`}>
                  {zones.map((z) => (
                    <polygon key={`z${z.id}`} points={ptStr(z.polygon || [])} fill={(z.color || kindColor(z.kind)) + "33"} stroke={z.color || kindColor(z.kind)} strokeWidth="2" vectorEffect="non-scaling-stroke" />
                  ))}
                  {lines.map((l) => (
                    <line key={`l${l.id}`} x1={l.point_a?.[0]} y1={l.point_a?.[1]} x2={l.point_b?.[0]} y2={l.point_b?.[1]} stroke={LINE_COLOR} strokeWidth="3" vectorEffect="non-scaling-stroke" />
                  ))}
                  {tool === "zone" && draft.length >= 2 && <polygon points={ptStr(draft)} fill="#ffffff22" stroke="#ffffff" strokeWidth="2" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />}
                  {tool === "line" && draft.length === 2 && <line x1={draft[0][0]} y1={draft[0][1]} x2={draft[1][0]} y2={draft[1][1]} stroke="#ffffff" strokeWidth="3" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />}
                  {draft.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="0.008" fill="#ffffff" stroke="#111" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
                </svg>
                <span className="absolute bottom-2 left-3 os-num text-[11px] text-white/70">{cameras.find((c) => c.id === camId)?.cam_name || "—"} · {draft.length} point(s)</span>
              </div>

              {canWrite && tool !== "select" && (
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder={`Nom de la ${tool === "line" ? "ligne" : "zone"} (ex. File guichets)`}
                    className="flex-1 min-w-[180px] px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1 outline-none focus:border-os-t3" />
                  {tool === "zone" && (
                    <select value={kind} onChange={(e) => setKind(e.target.value)} className="px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1">
                      {ZONE_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                  )}
                  {tool === "zone" && (
                    <input type="number" min="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="Seuil (optionnel)" title="Seuil d'attroupement"
                      className="w-36 px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1" />
                  )}
                  <button onClick={undoPoint} disabled={!draft.length} className="px-3 py-2 rounded-os text-[13px] border border-os-border text-os-t2 disabled:opacity-40">↶ Point</button>
                  <button onClick={save} className="px-4 py-2 rounded-os text-[13px] font-semibold bg-os-cta text-white hover:bg-os-cta-hover">Enregistrer</button>
                </div>
              )}
              {msg && <p className="text-[13px] text-os-red mt-2">{msg}</p>}
            </Card>
          </div>

          <div className="space-y-4">
            <Card className="p-5">
              <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Zones configurées ({zones.length})</h3>
              {zones.length === 0 ? (
                <p className="text-[13px] text-os-t3">Aucune zone sur cette caméra.</p>
              ) : (
                <ul className="space-y-2.5">
                  {zones.map((z) => (
                    <li key={z.id} className="flex items-center justify-between gap-2 rounded-os border border-os-border p-2.5">
                      <span className="flex items-center gap-2.5 min-w-0">
                        <span className="h-3 w-3 rounded-sm shrink-0" style={{ backgroundColor: z.color || kindColor(z.kind) }} />
                        <span className="min-w-0">
                          <span className="block text-[13px] font-semibold text-os-t1 truncate">{z.name}</span>
                          <span className="block text-[11px] text-os-t3">{kindLabel(z.kind)}{z.threshold ? ` · seuil ${z.threshold}` : ""} · polygone · {(z.polygon || []).length} pts</span>
                        </span>
                      </span>
                      {canWrite && <button onClick={() => delZone(z.id)} className="text-[12px] text-os-red hover:underline shrink-0">Suppr.</button>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card className="p-5">
              <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Lignes de comptage ({lines.length})</h3>
              {lines.length === 0 ? (
                <p className="text-[13px] text-os-t3">Aucune ligne sur cette caméra.</p>
              ) : (
                <ul className="space-y-2.5">
                  {lines.map((l) => (
                    <li key={l.id} className="flex items-center justify-between gap-2 rounded-os border border-os-border p-2.5">
                      <span className="flex items-center gap-2.5 min-w-0">
                        <span className="h-3 w-3 rounded-sm shrink-0" style={{ backgroundColor: LINE_COLOR }} />
                        <span className="text-[13px] font-semibold text-os-t1 truncate">{l.name}</span>
                      </span>
                      {canWrite && <button onClick={() => delLine(l.id)} className="text-[12px] text-os-red hover:underline shrink-0">Suppr.</button>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {/* <div className="rounded-os border border-os-border bg-os-card p-3.5">
              <p className="text-[12px] text-os-t3">ⓘ Les zones ne suivent aucun individu. Elles comptent des présences anonymes dans un périmètre.</p>
            </div> */}
          </div>
        </div>
      </div>
    </OsShell>
  );
}

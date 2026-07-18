"use client";

/**
 * Éditeur de zones & lignes de comptage.
 *
 * On choisit une caméra, on voit son flux live (CameraStream / WebRTC) et on
 * DESSINE par-dessus, sur un calque SVG en coordonnées NORMALISÉES [0,1]
 * (viewBox 0 0 1 1, preserveAspectRatio="none" → aligné sur la vidéo object-fill).
 * Les tracés sont donc indépendants de la résolution.
 *
 * Outils : « Zone » (polygone : clics successifs, ≥ 3 points) et « Ligne » (2 clics).
 * Sauvegarde via les proxys /api/zones et /api/zones/lines.
 */
import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import CameraStream from "../live/CameraStream";

const ZONE_KINDS = [
  { value: "occupancy", label: "Occupation", color: "#2563eb" },
  { value: "queue", label: "File d'attente", color: "#d97706" },
  { value: "crowd", label: "Attroupement", color: "#dc2626" },
  { value: "generic", label: "Générique", color: "#16a34a" },
];
const kindColor = (k) => (ZONE_KINDS.find((z) => z.value === k)?.color || "#16a34a");
const kindLabel = (k) => (ZONE_KINDS.find((z) => z.value === k)?.label || k);
const LINE_COLOR = "#f59e0b";

export default function ZonesPage() {
  const user = useAuth();
  const role = user?.role || "viewer";
  const canWrite = ["admin", "user"].includes(role);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const [cameras, setCameras] = useState([]);
  const [camId, setCamId] = useState(null);
  const [zones, setZones] = useState([]);
  const [lines, setLines] = useState([]);

  const [tool, setTool] = useState("select"); // "select" | "zone" | "line"
  const [draft, setDraft] = useState([]);      // points en cours : [[x,y], ...]
  const [name, setName] = useState("");
  const [kind, setKind] = useState("occupancy");
  const [msg, setMsg] = useState("");

  // ── Chargement des caméras ────────────────────────────────────────────────
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

  // ── Chargement des zones + lignes de la caméra sélectionnée ────────────────
  const loadShapes = useCallback(async (id) => {
    if (id == null) return;
    const [zr, lr] = await Promise.all([
      fetchWithRefresh(`/api/zones?camera_id=${id}`),
      fetchWithRefresh(`/api/zones/lines?camera_id=${id}`),
    ]);
    setZones(zr?.ok ? await zr.json() : []);
    setLines(lr?.ok ? await lr.json() : []);
  }, []);

  useEffect(() => {
    setDraft([]);
    setTool("select");
    setMsg("");
    loadShapes(camId);
  }, [camId, loadShapes]);

  // ── Dessin ─────────────────────────────────────────────────────────────────
  const onSvgClick = (e) => {
    if (!canWrite || tool === "select") return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    const pt = [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
    setDraft((d) => (tool === "line" ? [...d, pt].slice(-2) : [...d, pt]));
  };

  const cancelDraft = () => { setDraft([]); setName(""); setMsg(""); setTool("select"); };
  const undoPoint = () => setDraft((d) => d.slice(0, -1));

  const save = async () => {
    setMsg("");
    if (!name.trim()) { setMsg("Le nom est requis."); return; }
    try {
      if (tool === "zone") {
        if (draft.length < 3) { setMsg("Un polygone exige au moins 3 points."); return; }
        const r = await fetchWithRefresh("/api/zones", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: camId, name: name.trim(), kind, polygon: draft, color: kindColor(kind) }),
        });
        if (!r?.ok) { setMsg("Échec de l'enregistrement de la zone."); return; }
      } else if (tool === "line") {
        if (draft.length < 2) { setMsg("Une ligne exige exactement 2 points."); return; }
        const r = await fetchWithRefresh("/api/zones/lines", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id: camId, name: name.trim(), point_a: draft[0], point_b: draft[1] }),
        });
        if (!r?.ok) { setMsg("Échec de l'enregistrement de la ligne."); return; }
      }
      cancelDraft();
      loadShapes(camId);
    } catch { setMsg("Erreur réseau."); }
  };

  const delZone = async (id) => { await fetchWithRefresh(`/api/zones/${id}`, { method: "DELETE" }); loadShapes(camId); };
  const delLine = async (id) => { await fetchWithRefresh(`/api/zones/lines/${id}`, { method: "DELETE" }); loadShapes(camId); };

  if (user && !["admin", "user", "viewer"].includes(role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/zones" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={role} />
          </main>
        </div>
      </div>
    );
  }

  const ptStr = (pts) => pts.map((p) => `${p[0]},${p[1]}`).join(" ");

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/zones" />
        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar title="Zones & comptage" subtitle="Dessinez des zones (occupation / file / attroupement) et des lignes de comptage" showSearch={false} />

          <div className="p-6 space-y-4">
            {/* Sélecteur de caméra */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Caméra</label>
              <select
                value={camId ?? ""}
                onChange={(e) => setCamId(Number(e.target.value))}
                className="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {cameras.length === 0 && <option value="">Aucune caméra</option>}
                {cameras.map((c) => <option key={c.id} value={c.id}>{c.cam_name || `Caméra ${c.id}`}</option>)}
              </select>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              {/* Vidéo + calque de dessin */}
              <div className="xl:col-span-2 space-y-3">
                <div className="relative w-full aspect-video bg-gray-950 rounded-2xl overflow-hidden border border-gray-200 dark:border-gray-800">
                  {camId != null && <CameraStream cameraId={camId} showStats={false} />}
                  <svg
                    viewBox="0 0 1 1"
                    preserveAspectRatio="none"
                    onClick={onSvgClick}
                    className={`absolute inset-0 w-full h-full ${tool !== "select" ? "cursor-crosshair" : ""}`}
                  >
                    {/* Zones existantes */}
                    {zones.map((z) => (
                      <polygon key={`z${z.id}`} points={ptStr(z.polygon || [])}
                        fill={(z.color || kindColor(z.kind)) + "33"}
                        stroke={z.color || kindColor(z.kind)} strokeWidth="2" vectorEffect="non-scaling-stroke" />
                    ))}
                    {/* Lignes existantes */}
                    {lines.map((l) => (
                      <line key={`l${l.id}`} x1={l.point_a?.[0]} y1={l.point_a?.[1]} x2={l.point_b?.[0]} y2={l.point_b?.[1]}
                        stroke={LINE_COLOR} strokeWidth="3" vectorEffect="non-scaling-stroke" />
                    ))}
                    {/* Tracé en cours */}
                    {tool === "zone" && draft.length >= 2 && (
                      <polygon points={ptStr(draft)} fill="#ffffff22" stroke="#ffffff" strokeWidth="2" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
                    )}
                    {tool === "line" && draft.length === 2 && (
                      <line x1={draft[0][0]} y1={draft[0][1]} x2={draft[1][0]} y2={draft[1][1]}
                        stroke="#ffffff" strokeWidth="3" strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
                    )}
                    {draft.map((p, i) => (
                      <circle key={i} cx={p[0]} cy={p[1]} r="0.008" fill="#ffffff" stroke="#111" strokeWidth="1" vectorEffect="non-scaling-stroke" />
                    ))}
                  </svg>
                </div>

                {/* Barre d'outils */}
                {canWrite ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3">
                    <button onClick={() => { setTool("zone"); setDraft([]); setMsg(""); }}
                      className={`px-3 py-2 rounded-lg text-sm font-medium ${tool === "zone" ? "bg-indigo-600 text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"}`}>
                      ▱ Nouvelle zone
                    </button>
                    <button onClick={() => { setTool("line"); setDraft([]); setMsg(""); }}
                      className={`px-3 py-2 rounded-lg text-sm font-medium ${tool === "line" ? "bg-amber-500 text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300"}`}>
                      ╱ Nouvelle ligne
                    </button>

                    {tool !== "select" && (
                      <>
                        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom"
                          className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                        {tool === "zone" && (
                          <select value={kind} onChange={(e) => setKind(e.target.value)}
                            className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white">
                            {ZONE_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                          </select>
                        )}
                        <span className="text-xs text-gray-500 dark:text-gray-400">{draft.length} point(s)</span>
                        <button onClick={undoPoint} disabled={!draft.length}
                          className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-50">↶ Annuler point</button>
                        <button onClick={save}
                          className="px-3 py-2 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-700 text-white">Enregistrer</button>
                        <button onClick={cancelDraft}
                          className="px-3 py-2 rounded-lg text-sm bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">Annuler</button>
                      </>
                    )}
                    {msg && <span className="text-sm text-rose-600 dark:text-rose-400">{msg}</span>}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 dark:text-gray-400">Lecture seule — votre rôle ne permet pas d'éditer les zones.</p>
                )}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Astuce : sélectionnez un outil, cliquez sur la vidéo pour poser les points
                  (zone = ≥ 3 points, ligne = 2 points), nommez, puis Enregistrer.
                </p>
              </div>

              {/* Liste des zones + lignes */}
              <div className="space-y-4">
                <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Zones ({zones.length})</h3>
                  {zones.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Aucune zone sur cette caméra.</p>
                  ) : (
                    <ul className="space-y-2">
                      {zones.map((z) => (
                        <li key={z.id} className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 min-w-0">
                            <span className="h-3 w-3 rounded-sm shrink-0" style={{ backgroundColor: z.color || kindColor(z.kind) }} />
                            <span className="text-sm text-gray-900 dark:text-white truncate">{z.name}</span>
                            <span className="text-xs text-gray-400">· {kindLabel(z.kind)}</span>
                          </span>
                          {canWrite && <button onClick={() => delZone(z.id)} className="text-xs text-rose-600 hover:underline shrink-0">Supprimer</button>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Lignes de comptage ({lines.length})</h3>
                  {lines.length === 0 ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Aucune ligne sur cette caméra.</p>
                  ) : (
                    <ul className="space-y-2">
                      {lines.map((l) => (
                        <li key={l.id} className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 min-w-0">
                            <span className="h-3 w-3 rounded-sm shrink-0" style={{ backgroundColor: LINE_COLOR }} />
                            <span className="text-sm text-gray-900 dark:text-white truncate">{l.name}</span>
                          </span>
                          {canWrite && <button onClick={() => delLine(l.id)} className="text-xs text-rose-600 hover:underline shrink-0">Supprimer</button>}
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

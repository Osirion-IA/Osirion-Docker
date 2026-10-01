"use client";

/**
 * Zones & comptage — section Configurer (thème clair). Éditeur interactif :
 * clic sur l'image caméra pour poser les sommets d'un polygone (zone) ou 2 points
 * (ligne de comptage). Les zones comptent des PRÉSENCES ANONYMES dans un périmètre.
 * Sauvegarde via /api/zones et /api/zones/lines.
 */
import { useState, useEffect, useCallback } from "react";
import { Video } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";
import { CORE_URL } from "../../../lib/publicUrls";
import CameraStream from "../live/CameraStream";
import GroupedCameraPicker from "../_osirion/GroupedCameraPicker";

const ZONE_KINDS = [
  { value: "occupancy", label: "Occupation", color: "#2f7fd1" },
  { value: "queue", label: "File d'attente", color: "#f5a623" },
  { value: "crowd", label: "Attroupement", color: "#e60027" },
  // Exclusion : rien n'y est détecté. À tracer sur un décor qui déclenche des
  // détections permanentes (affiche, écran, reflet dans une vitre).
  { value: "ignore", label: "Zone ignorée", color: "#7c8695" },
  // Poste d'agent : suivi de l'occupation pendant les heures de travail du
  // régime horaire rattaché, pour repérer les absences.
  { value: "presence", label: "Poste d'agent", color: "#8b5cf6" },
  { value: "generic", label: "Générique", color: "#1faa59" },
];
// Aide contextuelle affichée sous le sélecteur de type.
const KIND_HINT = {
  occupancy: "Compte les personnes présentes dans le polygone.",
  queue: "File d'attente : longueur et temps d'attente.",
  crowd: "Alerte quand l'effectif dépasse le seuil pendant quelques secondes.",
  ignore: "Aucune détection retenue ici — à poser sur un décor trompeur (affiche, écran, reflet).",
  presence: "Poste d'agent : signale les absences pendant les heures de travail du régime choisi.",
  generic: "Zone repère, sans traitement particulier.",
};
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
  // Délai de confirmation : vide = valeur par défaut du moteur (5 s), 0 = immédiat.
  const [minPresence, setMinPresence] = useState("");
  // Régime horaire d'une zone « Poste d'agent » (jours, heures, fuseau, tolérance).
  const [schedules, setSchedules] = useState([]);
  const [scheduleId, setScheduleId] = useState("");
  const [groups, setGroups] = useState([]);
  const [configured, setConfigured] = useState({});   // { camId: { zones, lines } }
  const [previewState, setPreviewState] = useState("idle"); // idle|loading|ready|error
  const [msg, setMsg] = useState("");

  const loadCameras = useCallback(async () => {
    const r = await fetchWithRefresh("/api/cameras");
    if (r?.ok) {
      const cams = await r.json();
      const list = Array.isArray(cams) ? cams : [];
      setCameras(list);
      setCamId((prev) => {
        if (prev != null || !list.length) return prev;
        const usable = list.find((c) => c.is_active && c.hik_status !== 2)
          || list.find((c) => c.is_active)
          || list.find((c) => c.hik_status === 1);
        return (usable || list[0]).id;
      });
    }
  }, []);

  useEffect(() => { loadCameras(); }, [loadCameras]);
  useEffect(() => {
    (async () => {
      const r = await fetchWithRefresh("/api/groups");
      if (r?.ok) { const g = await r.json(); setGroups(Array.isArray(g) ? g : []); }
    })();
  }, []);
  // Régimes horaires actifs : proposés au tracé d'une zone « Poste d'agent ».
  useEffect(() => {
    (async () => {
      const r = await fetchWithRefresh("/api/work-schedules?active_only=true");
      if (r?.ok) { const s = await r.json(); setSchedules(Array.isArray(s) ? s : []); }
    })();
  }, []);

  // Index « quelles caméras sont DÉJÀ configurées » : { camId: { zones, lines } }.
  // Les deux endpoints acceptent l'absence de camera_id → tout le parc en 2 appels
  // (quelques dizaines de lignes au total). Sert à épingler ces caméras en tête du
  // sélecteur, pour ne plus avoir à fouiller le catalogue afin de les retrouver.
  const loadConfigured = useCallback(async () => {
    const [zr, lr] = await Promise.all([
      fetchWithRefresh("/api/zones"),
      fetchWithRefresh("/api/zones/lines"),
    ]);
    const idx = {};
    const tally = (rows, key) => {
      for (const r of Array.isArray(rows) ? rows : []) {
        if (r?.camera_id == null) continue;
        if (!idx[r.camera_id]) idx[r.camera_id] = { zones: 0, lines: 0 };
        idx[r.camera_id][key] += 1;
      }
    };
    tally(zr?.ok ? await zr.json() : [], "zones");
    tally(lr?.ok ? await lr.json() : [], "lines");
    setConfigured(idx);
  }, []);

  const loadShapes = useCallback(async (id) => {
    if (id == null) return;
    const [zr, lr] = await Promise.all([
      fetchWithRefresh(`/api/zones?camera_id=${id}`),
      fetchWithRefresh(`/api/zones/lines?camera_id=${id}`),
    ]);
    setZones(zr?.ok ? await zr.json() : []);
    setLines(lr?.ok ? await lr.json() : []);
    // Point d'accroche unique : loadShapes est déjà rappelé après chaque création
    // et chaque suppression → l'index reste à jour sans autre câblage.
    loadConfigured();
  }, [loadConfigured]);

  useEffect(() => { setDraft([]); setTool("select"); setMsg(""); loadShapes(camId); }, [camId, loadShapes]);

  // Prévisualisation d'une caméra du catalogue HikCentral NON ingérée : on demande
  // au Core de créer un chemin MediaMTX `preview<id>` (transcodé, à la demande) →
  // le flux est visible AVANT toute configuration, sans démarrer le traitement IA.
  useEffect(() => {
    const cam = cameras.find((c) => c.id === camId);
    const uningested = cam?.source_type === "hikcentral" && !cam?.is_active;
    if (camId == null || !uningested) { setPreviewState("idle"); return; }
    let cancelled = false;
    setPreviewState("loading");
    (async () => {
      try {
        const res = await fetch(`${CORE_URL}/api/cameras/${camId}/preview`, { method: "POST" });
        if (!cancelled) setPreviewState(res.ok ? "ready" : "error");
      } catch { if (!cancelled) setPreviewState("error"); }
    })();
    return () => { cancelled = true; };
  }, [camId, cameras]);

  const onSvgClick = (e) => {
    if (!canWrite || tool === "select") return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    const pt = [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
    setDraft((d) => (tool === "line" ? [...d, pt].slice(-2) : [...d, pt]));
  };
  const cancelDraft = () => { setDraft([]); setName(""); setThreshold(""); setMinPresence(""); setScheduleId(""); setMsg(""); setTool("select"); };
  const undoPoint = () => setDraft((d) => d.slice(0, -1));

  const save = async () => {
    setMsg("");
    if (!name.trim()) { setMsg("Le nom est requis."); return; }
    try {
      if (tool === "zone") {
        if (draft.length < 3) { setMsg("Un polygone exige au moins 3 points."); return; }
        // Sans régime, un poste ne serait JAMAIS surveillé (le moteur ne sait pas
        // quand il devrait être occupé) — mieux vaut le refuser ici que de laisser
        // croire à une surveillance active.
        if (kind === "presence" && !scheduleId) {
          setMsg("Choisissez un régime horaire : sans lui, ce poste ne serait pas surveillé.");
          return;
        }
        const r = await fetchWithRefresh("/api/zones", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            camera_id: camId, name: name.trim(), kind, polygon: draft, color: kindColor(kind),
            threshold: (kind !== "ignore" && threshold) ? Number(threshold) : null,
            // `0` est falsy en JS et c'est justement la valeur qui désarme le délai
            // (comptage immédiat) : on teste la chaîne vide, pas la véracité.
            // null = la zone suit le défaut du moteur.
            min_presence_s: (kind !== "ignore" && minPresence !== "") ? Number(minPresence) : null,
            work_schedule_id: kind === "presence" && scheduleId ? Number(scheduleId) : null,
          }),
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
      cancelDraft(); loadShapes(camId); loadCameras();  // is_active peut basculer (activation HikCentral)
    } catch { setMsg("Erreur réseau."); }
  };
  const delZone = async (id) => { await fetchWithRefresh(`/api/zones/${id}`, { method: "DELETE" }); loadShapes(camId); };
  const delLine = async (id) => { await fetchWithRefresh(`/api/zones/lines/${id}`, { method: "DELETE" }); loadShapes(camId); };
  const updateZoneSchedule = async (zoneId, nextScheduleId) => {
    setMsg("");
    const r = await fetchWithRefresh(`/api/zones/${zoneId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ work_schedule_id: Number(nextScheduleId) }),
    });
    if (!r?.ok) {
      const d = await r?.json().catch(() => null);
      setMsg(d?.detail || "Impossible de réaffecter ce régime horaire.");
      return;
    }
    loadShapes(camId);
  };

  const selectedCam = cameras.find((c) => c.id === camId) || null;
  // Caméra du catalogue HikCentral pas encore ingérée → aucun flux MediaMTX tant
  // qu'elle n'a pas été activée (1re zone). On affiche un placeholder explicite.
  const isUningested = selectedCam?.source_type === "hikcentral" && !selectedCam?.is_active;

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
            <GroupedCameraPicker
              cameras={cameras} groups={groups} value={camId} onChange={setCamId}
              configured={configured}
            />
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
                {camId != null && (isUningested ? (
                  previewState === "ready" ? (
                    // Flux de prévisualisation (chemin preview<id>, sans traitement IA).
                    <CameraStream cameraId={camId} streamPath={`preview${camId}`} showStats={false} showPresenceZones={false} />
                  ) : (
                    <div className="absolute inset-0 grid place-items-center text-center px-6">
                      <div>
                        {previewState === "loading" ? (
                          <>
                            <div className="h-8 w-8 mx-auto mb-3 rounded-full border-2 border-white/40 border-t-transparent os-anim-spin" />
                            <p className="text-[13px] text-white/80">Préparation de la prévisualisation…</p>
                            <p className="text-[12px] text-white/50 mt-1">Première connexion HikCentral — quelques secondes.</p>
                          </>
                        ) : (
                          <>
                            <Video className="h-8 w-8 mx-auto mb-3 text-white/40" strokeWidth={1.6} />
                            <p className="text-[13px] text-white/80">Prévisualisation indisponible.</p>
                            <p className="text-[12px] text-white/50 mt-1">Liaison agence muette ? Vous pouvez tout de même dessiner une zone pour l'activer.</p>
                          </>
                        )}
                      </div>
                    </div>
                  )
                ) : (
                  <CameraStream cameraId={camId} showStats={false} showPresenceZones={false} />
                ))}
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
                  {tool === "zone" && kind !== "ignore" && (
                    <input type="number" min="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="Seuil (optionnel)" title="Seuil d'attroupement"
                      className="w-36 px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1" />
                  )}
                  {tool === "zone" && kind === "presence" && (
                    <select value={scheduleId} onChange={(e) => setScheduleId(e.target.value)}
                      title="Jours et heures de travail appliqués à ce poste"
                      className="px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1">
                      <option value="">— Régime horaire —</option>
                      {schedules.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  )}
                  {tool === "zone" && kind !== "ignore" && (
                    <input type="number" min="0" step="0.5" value={minPresence} onChange={(e) => setMinPresence(e.target.value)}
                      placeholder="Délai 5 s" title="Secondes de présence avant de compter une personne. Vide = 5 s. 0 = immédiat (intrusion)."
                      className="w-36 px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1" />
                  )}
                  <button onClick={undoPoint} disabled={!draft.length} className="px-3 py-2 rounded-os text-[13px] border border-os-border text-os-t2 disabled:opacity-40">↶ Point</button>
                  <button onClick={save} className="px-4 py-2 rounded-os text-[13px] font-semibold bg-os-cta text-white hover:bg-os-cta-hover">Enregistrer</button>
                </div>
              )}
              {canWrite && tool === "zone" && (
                <>
                  <p className="text-[12px] text-os-t3 mt-2">{KIND_HINT[kind]}</p>
                  {kind !== "ignore" && (
                    <p className="text-[12px] text-os-t3 mt-1">
                      <span className="text-os-t2 font-semibold">Délai</span> : une personne n'est comptée
                      qu'après être restée {minPresence === "" ? "5" : minPresence} s d'affilée dans la zone —
                      quelqu'un qui ne fait que passer, ou qui s'arrête une seconde, est ignoré.
                      Mettez <span className="os-num">0</span> pour une zone où l'alerte doit être immédiate (intrusion).
                    </p>
                  )}
                </>
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
                          <span className="block text-[11px] text-os-t3">
                            {kindLabel(z.kind)}{z.threshold ? ` · seuil ${z.threshold}` : ""}
                            {/* `!= null` : garde le 0 (comptage immédiat), écarte null/undefined. */}
                            {z.min_presence_s != null && (z.min_presence_s === 0 ? " · comptage immédiat" : ` · délai ${z.min_presence_s} s`)}
                            {/* Un poste sans régime n'est pas surveillé : le dire ici, pas seulement à la création. */}
                            {z.kind === "presence" && !canWrite && (z.schedule ? ` · ${z.schedule.name}` : " · ⚠ sans régime, non surveillé")}
                            {" · polygone · "}{(z.polygon || []).length} pts
                          </span>
                          {z.kind === "presence" && canWrite && (
                            <select value={z.schedule?.id || ""}
                              onChange={(e) => updateZoneSchedule(z.id, e.target.value)}
                              className="mt-1 max-w-full rounded-os border border-os-border bg-os-card px-2 py-1 text-[11px] text-os-t2">
                              <option value="" disabled>⚠ Choisir un régime actif</option>
                              {schedules.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                          )}
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

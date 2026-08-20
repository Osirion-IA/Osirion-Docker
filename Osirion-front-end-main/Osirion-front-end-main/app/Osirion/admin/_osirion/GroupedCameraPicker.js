"use client";

// Sélecteur de caméra GROUPÉ PAR SITE (éditeur de Zones). Remplace le <select>
// plat : le catalogue HikCentral compte des dizaines de caméras réparties par
// agence → recherche + regroupement par site + pastille de statut facilitent la
// sélection. Un tag « catalogue » signale les caméras non encore configurées
// (activées à la 1re zone).
//
// `configured` ({ camId: { zones, lines } }) épingle EN TÊTE les caméras qui ont
// déjà des zones/lignes : ce sont celles sur lesquelles on revient, et les
// retrouver imposait sinon de fouiller tout le catalogue. Elles restent AUSSI
// listées dans leur site plus bas (le catalogue reste complet). Comme cette liste
// épinglée est à plat, chaque ligne rappelle le SITE : sans lui, « Camera 01 » ne
// désigne rien dans un parc où le même nom revient d'une agence à l'autre.
import { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Search, Video } from "lucide-react";
import { groupCamerasBySite, catalogStatus, siteLabel, TONE_COLOR } from "../../../lib/cameraGroups";

function Dot({ tone }) {
  return <span className="h-2 w-2 rounded-full shrink-0" style={{ background: TONE_COLOR[tone] }} />;
}

/** « 2 zones · 1 ligne » — ce qui est déjà tracé sur la caméra. */
function configSummary(cfg) {
  if (!cfg) return "";
  const parts = [];
  if (cfg.zones) parts.push(`${cfg.zones} zone${cfg.zones > 1 ? "s" : ""}`);
  if (cfg.lines) parts.push(`${cfg.lines} ligne${cfg.lines > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

export default function GroupedCameraPicker({ cameras, groups, value, onChange, configured = {} }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const rootRef = useRef(null);

  const selected = useMemo(() => cameras.find((c) => c.id === value) || null, [cameras, value]);

  const sites = useMemo(() => {
    const grouped = groupCamerasBySite(cameras, groups);
    const needle = q.trim().toLowerCase();
    if (!needle) return grouped;
    return grouped
      .map((s) => ({
        ...s,
        cameras: s.cameras.filter(
          (c) =>
            (c.cam_name || "").toLowerCase().includes(needle) ||
            s.name.toLowerCase().includes(needle)
        ),
      }))
      .filter((s) => s.cameras.length > 0);
  }, [cameras, groups, q]);

  // Caméras déjà configurées, filtrées par la MÊME recherche (nom ou site) et
  // triées par site puis par nom, pour que l'ordre reste prévisible.
  const configuredCams = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (cameras || [])
      .filter((c) => {
        const cfg = configured[c.id];
        if (!cfg || (!cfg.zones && !cfg.lines)) return false;
        if (!needle) return true;
        const site = siteLabel(c, groups).toLowerCase();
        return (c.cam_name || "").toLowerCase().includes(needle) || site.includes(needle);
      })
      .sort((a, b) => {
        const s = siteLabel(a, groups).localeCompare(siteLabel(b, groups), "fr");
        return s !== 0 ? s : (a.cam_name || "").localeCompare(b.cam_name || "", "fr");
      });
  }, [cameras, groups, configured, q]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const selStatus = selected ? catalogStatus(selected) : null;
  const total = cameras.length;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="min-w-[240px] flex items-center gap-2 rounded-os border border-os-border bg-os-card px-3 py-2 text-[13px] text-os-t1 outline-none hover:border-os-t3"
      >
        {selStatus ? <Dot tone={selStatus.tone} /> : <Video className="h-4 w-4 text-os-t4" />}
        <span className="min-w-0 flex-1 text-left truncate">
          {selected ? selected.cam_name || `Caméra ${selected.id}` : "Sélectionner une caméra"}
        </span>
        <ChevronDown className={`h-4 w-4 text-os-t4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-1.5 w-[340px] max-w-[85vw] rounded-os-lg border border-os-border bg-os-card shadow-lg">
          <div className="p-2 border-b border-os-border">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-os-t4" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={`Rechercher parmi ${total} caméra(s)…`}
                className="w-full rounded-os border border-os-border bg-os-card-2 pl-8 pr-3 py-1.5 text-[13px] text-os-t1 outline-none focus:border-os-t3"
              />
            </div>
          </div>
          <div className="max-h-[380px] overflow-y-auto py-1">
            {sites.length === 0 && configuredCams.length === 0 && (
              <p className="px-3 py-6 text-center text-[13px] text-os-t3">Aucune caméra ne correspond.</p>
            )}

            {configuredCams.length > 0 && (
              <div className="mb-1 border-b border-os-border pb-1">
                <div className="sticky top-0 flex items-center justify-between bg-os-card px-3 py-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-os-t3">Déjà configurées</span>
                  <span className="os-num text-[11px] text-os-t4">{configuredCams.length}</span>
                </div>
                {configuredCams.map((c) => {
                  const st = catalogStatus(c);
                  const active = c.id === value;
                  return (
                    <button
                      key={`cfg-${c.id}`}
                      type="button"
                      onClick={() => { onChange(c.id); setOpen(false); setQ(""); }}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-os-card-2 ${active ? "bg-os-card-2" : ""}`}
                    >
                      <Dot tone={st.tone} />
                      <span className="min-w-0 flex-1">
                        <span className={`block truncate text-[13px] ${active ? "font-semibold text-os-t1" : "text-os-t2"}`}>
                          {c.cam_name || `Caméra ${c.id}`}
                        </span>
                        {/* Site + contenu déjà tracé : de quoi reconnaître la caméra
                            hors de son groupe, et savoir ce qui s'y trouve déjà. */}
                        <span className="block truncate text-[11px] text-os-t4">
                          {siteLabel(c, groups)} · {configSummary(configured[c.id])}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {sites.map((s) => (
              <div key={s.id} className="mb-1">
                <div className="sticky top-0 flex items-center justify-between bg-os-card px-3 py-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-os-t3 truncate">{s.name}</span>
                  <span className="os-num text-[11px] text-os-t4">{s.cameras.length}</span>
                </div>
                {s.cameras.map((c) => {
                  const st = catalogStatus(c);
                  const isCatalog = c.source_type === "hikcentral" && !c.is_active;
                  const active = c.id === value;
                  return (
                    <button
                      key={`${s.id}-${c.id}`}
                      type="button"
                      onClick={() => { onChange(c.id); setOpen(false); setQ(""); }}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-[13px] hover:bg-os-card-2 ${active ? "bg-os-card-2" : ""}`}
                    >
                      <Dot tone={st.tone} />
                      <span className={`min-w-0 flex-1 truncate ${active ? "font-semibold text-os-t1" : "text-os-t2"}`}>
                        {c.cam_name || `Caméra ${c.id}`}
                      </span>
                      {isCatalog && (
                        <span className="shrink-0 rounded-os border border-os-border px-1.5 py-0.5 text-[10px] text-os-t4">catalogue</span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

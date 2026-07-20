"use client";

// Sélecteur de caméra GROUPÉ PAR SITE (éditeur de Zones). Remplace le <select>
// plat : le catalogue HikCentral compte des dizaines de caméras réparties par
// agence → recherche + regroupement par site + pastille de statut facilitent la
// sélection. Un tag « catalogue » signale les caméras non encore configurées
// (activées à la 1re zone).
import { useState, useRef, useEffect, useMemo } from "react";
import { ChevronDown, Search, Video } from "lucide-react";
import { groupCamerasBySite, catalogStatus, TONE_COLOR } from "../../../lib/cameraGroups";

function Dot({ tone }) {
  return <span className="h-2 w-2 rounded-full shrink-0" style={{ background: TONE_COLOR[tone] }} />;
}

export default function GroupedCameraPicker({ cameras, groups, value, onChange }) {
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
            {sites.length === 0 && (
              <p className="px-3 py-6 text-center text-[13px] text-os-t3">Aucune caméra ne correspond.</p>
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

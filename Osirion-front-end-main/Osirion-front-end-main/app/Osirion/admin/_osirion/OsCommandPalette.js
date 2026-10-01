"use client";

// Palette de navigation Osirion (Cmd/Ctrl+K) — recherche tous les écrans.
// Extraite de l'ancienne topbar : le déclencheur VISUEL (loupe) a disparu avec
// elle, le raccourci clavier reste. Montée une fois par la coquille (OsShell).
import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

export default function OsCommandPalette({ sections }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const router = useRouter();

  const items = useMemo(
    () => (sections || []).flatMap((s) => s.screens.map((sc) => ({ ...sc, section: s.label }))),
    [sections]
  );
  const results = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? items.filter((it) => it.label.toLowerCase().includes(n) || it.section.toLowerCase().includes(n)) : items;
  }, [items, q]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); }
      else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (href) => { setOpen(false); setQ(""); router.push(href); };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-start justify-center pt-[12vh] px-4" onClick={() => setOpen(false)}>
      <div className="w-full max-w-lg rounded-os-lg border border-[#2e3b3c] bg-[#141d1f] shadow-[0_16px_44px_rgba(0,0,0,.55)] overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2.5 px-4 border-b border-[#2e3b3c]">
          <Search className="h-4 w-4 text-[#8d9799] shrink-0" />
          <input
            autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && results[0]) go(results[0].href); }}
            placeholder="Rechercher une page…"
            className="flex-1 bg-transparent py-3.5 text-[14px] text-white placeholder:text-[#6c7679] outline-none"
          />
          <kbd className="os-num text-[10px] text-[#6c7679] border border-[#2e3b3c] rounded px-1.5 py-0.5">Échap</kbd>
        </div>
        <div className="max-h-[52vh] overflow-y-auto py-1.5">
          {results.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-[#8d9799]">Aucune page ne correspond.</p>
          ) : results.map((it) => {
            const Icon = it.icon;
            return (
              <button key={it.href} onClick={() => go(it.href)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-white/5">
                <Icon className="h-4 w-4 text-[#8d9799] shrink-0" strokeWidth={1.9} />
                <span className="text-[13px] text-[#c4cccd] flex-1 truncate">{it.label}</span>
                <span className="text-[11px] text-[#6c7679] shrink-0">{it.section}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

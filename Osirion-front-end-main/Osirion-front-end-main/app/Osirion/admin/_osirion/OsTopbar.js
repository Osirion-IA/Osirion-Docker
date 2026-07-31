"use client";

// Topbar Osirion — noire dans les deux thèmes. Logo + 3 sections (point d'état) +
// recherche, cloche (badge alertes rouge), aide, menu profil.
import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Bell, ChevronDown, LogOut, User, Settings } from "lucide-react";
import OsLogo from "./OsLogo";

export default function OsTopbar({ sections, alertsCount = 0, user }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [q, setQ] = useState("");
  const router = useRouter();

  // Recherche = palette de navigation sur tous les écrans (Cmd/Ctrl+K).
  const items = useMemo(() => (sections || []).flatMap((s) => s.screens.map((sc) => ({ ...sc, section: s.label }))), [sections]);
  const results = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? items.filter((it) => it.label.toLowerCase().includes(n) || it.section.toLowerCase().includes(n)) : items;
  }, [items, q]);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
      else if (e.key === "Escape") setSearchOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const go = (href) => { setSearchOpen(false); setQ(""); router.push(href); };

  const initials = (user?.fullName || user?.email || "?")
    .split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");

  const logout = async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* */ }
    window.location.href = "/";
  };

  return (
    <>
    <header className="fixed top-0 inset-x-0 z-40 h-[52px] bg-os-topbar border-b border-black/60 flex items-center pr-4 pl-5 gap-6">
      <Link href="/Osirion/admin/cockpit" className="shrink-0"><OsLogo /></Link>

      <div className="ml-auto flex items-center gap-1.5">
        <button onClick={() => setSearchOpen(true)} className="h-9 w-9 grid place-items-center rounded-os text-[#8a929b] hover:text-white hover:bg-white/5" aria-label="Rechercher">
          <Search className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </button>

        <Link href="/Osirion/admin/alerts" className="relative h-9 w-9 grid place-items-center rounded-os text-[#8a929b] hover:text-white hover:bg-white/5" aria-label="Centre d'alertes">
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.9} />
          {alertsCount > 0 && (
            <span className="os-num absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 grid place-items-center rounded-full bg-os-red text-white text-[10px] font-semibold leading-none">
              {alertsCount > 99 ? "99+" : alertsCount}
            </span>
          )}
        </Link>

        <div className="mx-1 h-6 w-px bg-white/10" />

        <div className="relative">
          <button
            onClick={() => setProfileOpen((o) => !o)}
            className="flex items-center gap-2.5 pl-1.5 pr-2 py-1 rounded-os hover:bg-white/5"
          >
            <span className="h-8 w-8 grid place-items-center rounded-os bg-[#2c333b] text-white text-[12px] font-semibold os-num">{initials}</span>
            <span className="text-left leading-tight hidden sm:block">
              <span className="block text-[13px] text-white font-medium">{user?.fullName || "Utilisateur"}</span>
              <span className="block text-[11px] text-[#8a929b] capitalize">{user?.role || ""}</span>
            </span>
            <ChevronDown className="h-4 w-4 text-[#8a929b]" />
          </button>

          {profileOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setProfileOpen(false)} />
              <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-64 rounded-os-lg border border-[#2c333b] bg-[#16191d] p-1.5 shadow-[0_16px_44px_rgba(0,0,0,.55)]">
                <div className="px-3 py-2.5 border-b border-[#2c333b]">
                  <p className="text-[13px] text-white font-medium truncate">{user?.fullName || "Utilisateur"}</p>
                  <p className="text-[11px] text-[#8a929b] truncate">{user?.email || ""}</p>
                </div>
                <div className="py-1">
                  <Link href="/Osirion/admin/system-status" onClick={() => setProfileOpen(false)}
                    className="flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-[#c3c8ce] hover:bg-white/5 hover:text-white">
                    <User className="h-4 w-4" /> Système &amp; accès
                  </Link>
                  {user?.role === "admin" && (
                    <Link href="/Osirion/admin/settings" onClick={() => setProfileOpen(false)}
                      className="flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-[#c3c8ce] hover:bg-white/5 hover:text-white">
                      <Settings className="h-4 w-4" /> Paramètres
                    </Link>
                  )}
                </div>
                <div className="pt-1 border-t border-[#2c333b]">
                  <button onClick={logout}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-[#f0a0a8] hover:bg-os-red hover:text-white">
                    <LogOut className="h-4 w-4" /> Se déconnecter
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>

    {searchOpen && (
      <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm flex items-start justify-center pt-[12vh] px-4" onClick={() => setSearchOpen(false)}>
        <div className="w-full max-w-lg rounded-os-lg border border-[#2c333b] bg-[#16191d] shadow-[0_16px_44px_rgba(0,0,0,.55)] overflow-hidden" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-2.5 px-4 border-b border-[#2c333b]">
            <Search className="h-4 w-4 text-[#8a929b] shrink-0" />
            <input
              autoFocus value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && results[0]) go(results[0].href); }}
              placeholder="Rechercher une page…"
              className="flex-1 bg-transparent py-3.5 text-[14px] text-white placeholder:text-[#6b7480] outline-none"
            />
            <kbd className="os-num text-[10px] text-[#6b7480] border border-[#2c333b] rounded px-1.5 py-0.5">Échap</kbd>
          </div>
          <div className="max-h-[52vh] overflow-y-auto py-1.5">
            {results.length === 0 ? (
              <p className="px-4 py-6 text-center text-[13px] text-[#8a929b]">Aucune page ne correspond.</p>
            ) : results.map((it) => {
              const Icon = it.icon;
              return (
                <button key={it.href} onClick={() => go(it.href)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-white/5">
                  <Icon className="h-4 w-4 text-[#8a929b] shrink-0" strokeWidth={1.9} />
                  <span className="text-[13px] text-[#c3c8ce] flex-1 truncate">{it.label}</span>
                  <span className="text-[11px] text-[#6b7480] shrink-0">{it.section}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    )}
    </>
  );
}

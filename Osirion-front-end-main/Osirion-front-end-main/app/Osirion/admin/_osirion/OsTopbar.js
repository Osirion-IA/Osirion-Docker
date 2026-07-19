"use client";

// Topbar Osirion — noire dans les deux thèmes. Logo + 3 sections (point d'état) +
// recherche, cloche (badge alertes rouge), aide, menu profil.
import { useState } from "react";
import Link from "next/link";
import { Search, Bell, HelpCircle, ChevronDown, LogOut, User } from "lucide-react";
import OsLogo from "./OsLogo";

export default function OsTopbar({ sections, activeKey, alertsCount = 0, user }) {
  const [profileOpen, setProfileOpen] = useState(false);

  const initials = (user?.fullName || user?.email || "?")
    .split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");

  const logout = async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* */ }
    window.location.href = "/";
  };

  return (
    <header className="fixed top-0 inset-x-0 z-40 h-[52px] bg-os-topbar border-b border-black/60 flex items-center pr-4 pl-5 gap-6">
      <Link href="/Osirion/admin/cockpit" className="shrink-0"><OsLogo /></Link>

      <nav className="flex items-center gap-1">
        {sections.map((s) => {
          const active = s.key === activeKey;
          const first = s.screens[0].href;
          return (
            <Link
              key={s.key}
              href={first}
              className={`group flex items-center gap-2 px-3.5 py-1.5 rounded-os text-[13px] transition-colors ${
                active ? "bg-white/10 text-white" : "text-[#8a929b] hover:text-[#c3c8ce]"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-os-green" : "bg-[#4b535c] group-hover:bg-[#6b7480]"}`} />
              <span className={active ? "font-medium" : ""}>{s.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <button className="h-9 w-9 grid place-items-center rounded-os text-[#8a929b] hover:text-white hover:bg-white/5" aria-label="Rechercher">
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

        <button className="h-9 w-9 grid place-items-center rounded-os text-[#8a929b] hover:text-white hover:bg-white/5" aria-label="Aide">
          <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.9} />
        </button>

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
  );
}

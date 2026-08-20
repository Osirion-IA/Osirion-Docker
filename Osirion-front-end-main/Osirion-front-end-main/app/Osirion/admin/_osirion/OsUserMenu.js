"use client";

// Menu utilisateur Osirion — pied de sidebar. Reprend À L'IDENTIQUE le menu de
// l'ancienne topbar (identité, Système & accès, Paramètres si admin, déconnexion) ;
// seul le déclencheur change : une pastille au PRÉNOM (8 caractères max) au lieu
// du bloc nom+rôle. Le panneau s'ouvre VERS LE HAUT (bouton collé au bas de l'écran).
import { useState } from "react";
import Link from "next/link";
import { LogOut, User, Settings } from "lucide-react";

// Longueur maximale affichée sur la pastille : au-delà, coupe avec une ellipse.
const MAX_LABEL = 8;

/** Étiquette du bouton : le prénom (ou le début de l'identifiant), ≤ MAX_LABEL car. */
function shortName(user) {
  const raw = (user?.fullName || user?.email || "Compte").split("@")[0].trim();
  const first = raw.split(/[\s._-]+/).filter(Boolean)[0] || raw;
  const cased = first.charAt(0).toUpperCase() + first.slice(1);
  return cased.length > MAX_LABEL ? `${cased.slice(0, MAX_LABEL - 1)}…` : cased;
}

export default function OsUserMenu({ user }) {
  const [open, setOpen] = useState(false);

  const label = shortName(user);

  const logout = async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* déconnexion best-effort */ }
    window.location.href = "/";
  };

  return (
    <div className="relative shrink-0 border-t border-os-sidebar-border px-3 py-2.5">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Compte — ${user?.fullName || user?.email || "utilisateur"}`}
        title={user?.fullName || user?.email || "Compte"}
        className={`h-9 max-w-full inline-flex items-center gap-2 pl-2.5 pr-3 rounded-os text-[13px] font-medium text-os-sidebar-t1 transition-colors ${
          open ? "bg-os-sidebar-active" : "bg-os-sidebar-hover hover:bg-os-sidebar-active"
        }`}
      >
        <User
          className={`h-[15px] w-[15px] shrink-0 ${open ? "text-os-primary" : "text-os-sidebar-t2"}`}
          strokeWidth={1.9}
        />
        <span className="truncate">{label}</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="absolute z-50 bottom-[calc(100%+6px)] left-2 right-2 rounded-os-lg border border-os-sidebar-border bg-os-sidebar p-1.5 shadow-[0_14px_38px_rgba(46,59,60,.18)]"
          >
            <div className="px-3 py-2.5 border-b border-os-sidebar-border">
              <p className="text-[13px] text-os-sidebar-t1 font-medium truncate">{user?.fullName || "Utilisateur"}</p>
              <p className="text-[11px] text-os-sidebar-t2 truncate">{user?.email || ""}</p>
              {user?.role && <p className="text-[11px] text-os-sidebar-t3 capitalize mt-0.5">{user.role}</p>}
            </div>
            <div className="py-1">
              <Link href="/Osirion/admin/system-status" onClick={() => setOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-os-sidebar-t2 hover:bg-os-sidebar-hover hover:text-os-sidebar-t1">
                <User className="h-4 w-4 shrink-0" /> Système &amp; accès
              </Link>
              {user?.role === "admin" && (
                <Link href="/Osirion/admin/settings" onClick={() => setOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-os-sidebar-t2 hover:bg-os-sidebar-hover hover:text-os-sidebar-t1">
                  <Settings className="h-4 w-4 shrink-0" /> Paramètres
                </Link>
              )}
            </div>
            <div className="pt-1 border-t border-os-sidebar-border">
              <button onClick={logout}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-os text-[13px] text-os-red hover:bg-os-red hover:text-white">
                <LogOut className="h-4 w-4 shrink-0" /> Se déconnecter
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

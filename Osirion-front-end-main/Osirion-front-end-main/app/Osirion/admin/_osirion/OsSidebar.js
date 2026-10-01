"use client";

// Sidebar Osirion — BLANCHE dans les deux thèmes (blanc de la charte Qwiper) et
// SEULE chrome de l'application (il n'y a plus de topbar). Trois étages : logo,
// accordéon de navigation (tous les écrans groupés par section, groupe actif
// ouvert), menu utilisateur en pied.
//
// Couleurs de marque : BLEU pour ce qui est ACTIF (accent, icône, pastille de
// section), NOIR de marque pour les libellés — le bleu ne passe pas le contraste
// en texte sur blanc (2,1:1). Le ROUGE ne sert plus qu'aux badges d'alertes.
//
// Le défilement est porté par le <nav> SEUL, pas par l'<aside> : sans ça, le
// panneau du menu utilisateur (qui déborde vers le haut) serait rogné par le
// conteneur de défilement.
import { useState, useEffect } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { activeScreenHref } from "./nav";
import OsLogo from "./OsLogo";
import OsUserMenu from "./OsUserMenu";

export default function OsSidebar({ sections, activeKey, activePath, alertsCount = 0, user }) {
  const [open, setOpen] = useState(() => new Set([activeKey]));

  // À la navigation vers une autre section, on ouvre son groupe (sans fermer les autres).
  useEffect(() => {
    setOpen((prev) => (prev.has(activeKey) ? prev : new Set(prev).add(activeKey)));
  }, [activeKey]);

  const toggle = (k) =>
    setOpen((prev) => {
      const n = new Set(prev);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });

  return (
    <aside className="shrink-0 w-[230px] bg-os-sidebar border-r border-os-sidebar-border sticky top-0 h-screen flex flex-col">
      <Link
        href="/Osirion/admin/cockpit"
        className="shrink-0 h-[52px] flex items-center px-4 border-b border-os-sidebar-border"
        aria-label="Accueil — Cockpit"
      >
        {/* Sidebar BLANCHE → logotype en version COULEUR (la version blanche y
            serait invisible). */}
        <OsLogo height={24} on="light" />
      </Link>

      <nav className="px-3 py-3 flex-1 min-h-0 overflow-y-auto space-y-1">
        {sections.map((s) => {
          const isOpen = open.has(s.key);
          const isActiveSection = s.key === activeKey;
          const activeHref = isActiveSection ? activeScreenHref(s, activePath) : null;
          const sectionBadge = s.screens.some((sc) => sc.badge === "alerts") && alertsCount > 0;
          return (
            <div key={s.key}>
              <button
                onClick={() => toggle(s.key)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-os text-[12px] font-semibold uppercase tracking-[0.1em] transition-colors ${
                  isActiveSection
                    ? "text-os-sidebar-t1"
                    : "text-os-sidebar-t2 hover:text-os-sidebar-t1"
                }`}
              >
                {/* Section active = BLEU de marque (le vert reste un état de santé). */}
                <span className={`h-1.5 w-1.5 rounded-full ${isActiveSection ? "bg-os-primary" : "bg-os-sidebar-t3"}`} />
                <span className="flex-1 text-left">{s.label}</span>
                {sectionBadge && !isOpen && (
                  <span className="os-num min-w-[18px] h-[18px] px-1 grid place-items-center rounded-full bg-os-red text-white text-[10px] font-semibold leading-none">
                    {alertsCount > 99 ? "99+" : alertsCount}
                  </span>
                )}
                <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${isOpen ? "" : "-rotate-90"}`} strokeWidth={2} />
              </button>

              {isOpen && (
                <div className="mt-0.5 mb-1.5 space-y-0.5">
                  {s.screens.map((sc) => {
                    const active = sc.href === activeHref;
                    const Icon = sc.icon;
                    const showBadge = sc.badge === "alerts" && alertsCount > 0;
                    return (
                      <Link
                        key={sc.href}
                        href={sc.href}
                        className={`relative flex items-center gap-3 pl-6 pr-3 py-2 rounded-os text-[13px] transition-colors ${
                          active
                            ? "bg-os-sidebar-active text-os-sidebar-t1 font-medium"
                            : "text-os-sidebar-t2 hover:text-os-sidebar-t1 hover:bg-os-sidebar-hover"
                        }`}
                      >
                        {/* Écran actif : accent + icône en BLEU de marque, libellé en
                            NOIR de marque (le bleu ne passe pas le contraste en texte).
                            Le ROUGE reste réservé aux seules alertes (badges ci-dessous). */}
                        {active && <span className="absolute left-1 top-1/2 -translate-y-1/2 h-6 w-[3px] rounded-r bg-os-primary" />}
                        <Icon
                          className={`h-[17px] w-[17px] shrink-0 ${active ? "text-os-primary" : ""}`}
                          strokeWidth={1.9}
                        />
                        <span className="truncate">{sc.label}</span>
                        {showBadge && (
                          <span className="os-num ml-auto min-w-[20px] h-5 px-1.5 grid place-items-center rounded-full bg-os-red text-white text-[11px] font-semibold leading-none">
                            {alertsCount > 99 ? "99+" : alertsCount}
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <OsUserMenu user={user} />
    </aside>
  );
}

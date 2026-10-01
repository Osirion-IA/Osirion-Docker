"use client";

// Coquille Osirion : sidebar blanche contextuelle (seule chrome de l'application,
// il n'y a plus de topbar) + zone de contenu dont le THÈME suit la section
// (Surveiller=sombre, autres=clair). La section active est déduite du chemin
// (usePathname) → deep-linking préservé.
//
// La topbar portait 3 contrôles : cloche (doublon du Centre d'alertes de la
// sidebar), loupe (la palette reste au clavier, Cmd/Ctrl+K) et menu profil
// (descendu en pied de sidebar). Sa suppression rend 52 px de hauteur utile à
// TOUS les écrans — la grille live et l'analytique en profitent directement.
//
// MOBILE (< lg) : la sidebar passe en tiroir hors écran et une barre de 52 px
// porte le bouton d'ouverture. Elle reprenait sinon 230 px sur une largeur de
// 390, et tout le contenu se retrouvait tronqué. Au-dessus de lg, cette barre
// disparaît et la mise en page d'origine est rendue à l'identique.
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { useAuth } from "../AuthContext";
import { SECTIONS, findSection } from "./nav";
import OsSidebar from "./OsSidebar";
import OsCommandPalette from "./OsCommandPalette";

export default function OsShell({ children, alertsCount = 0 }) {
  const pathname = usePathname() || "";
  const user = useAuth();
  const section = findSection(pathname);
  const [menuOpen, setMenuOpen] = useState(false);

  // Changer d'écran referme le tiroir — y compris sur une navigation qui ne
  // passe pas par un clic dans le menu (retour navigateur, palette de commandes).
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // Échap referme, comme tout panneau superposé.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e) => { if (e.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div data-os-theme={section.theme} className="min-h-screen bg-os-bg text-os-t1 font-sans">
      <div className="flex">
        {/* Voile : seulement sous lg, et seulement tiroir ouvert. */}
        {menuOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            onClick={() => setMenuOpen(false)}
            aria-hidden="true"
          />
        )}

        <OsSidebar
          sections={SECTIONS}
          activeKey={section.key}
          activePath={pathname}
          alertsCount={alertsCount}
          user={user}
          mobileOpen={menuOpen}
          onClose={() => setMenuOpen(false)}
        />

        <main className="flex-1 min-w-0">
          {/* Barre d'ouverture — sous lg uniquement. */}
          <div className="lg:hidden sticky top-0 z-30 h-[52px] flex items-center gap-3 px-4 bg-os-sidebar border-b border-os-sidebar-border">
            <button
              onClick={() => setMenuOpen(true)}
              aria-label="Ouvrir le menu"
              aria-expanded={menuOpen}
              className="h-9 w-9 -ml-1.5 grid place-items-center rounded-os text-os-sidebar-t2 hover:text-os-sidebar-t1 hover:bg-os-sidebar-hover"
            >
              <Menu className="h-5 w-5" strokeWidth={1.9} />
            </button>
            <span className="text-[13px] font-semibold text-os-sidebar-t1 truncate">{section.title}</span>
            {alertsCount > 0 && (
              <span className="os-num ml-auto min-w-[20px] h-5 px-1.5 grid place-items-center rounded-full bg-os-red text-white text-[11px] font-semibold leading-none">
                {alertsCount > 99 ? "99+" : alertsCount}
              </span>
            )}
          </div>
          {children}
        </main>
      </div>
      <OsCommandPalette sections={SECTIONS} />
    </div>
  );
}

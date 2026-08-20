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
import { usePathname } from "next/navigation";
import { useAuth } from "../AuthContext";
import { SECTIONS, findSection } from "./nav";
import OsSidebar from "./OsSidebar";
import OsCommandPalette from "./OsCommandPalette";

export default function OsShell({ children, alertsCount = 0, camsOnline = 0, camsTotal = 0 }) {
  const pathname = usePathname() || "";
  const user = useAuth();
  const section = findSection(pathname);

  return (
    <div data-os-theme={section.theme} className="min-h-screen bg-os-bg text-os-t1 font-sans">
      <div className="flex">
        <OsSidebar
          sections={SECTIONS}
          activeKey={section.key}
          activePath={pathname}
          alertsCount={alertsCount}
          user={user}
        />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
      <OsCommandPalette sections={SECTIONS} />
    </div>
  );
}

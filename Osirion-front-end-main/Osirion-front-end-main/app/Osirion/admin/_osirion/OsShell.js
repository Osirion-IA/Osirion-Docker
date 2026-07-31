"use client";

// Coquille Osirion : topbar noire (3 sections) + sidebar charbon contextuelle +
// zone de contenu dont le THÈME suit la section (Surveiller=sombre, autres=clair).
// La section active est déduite du chemin (usePathname) → deep-linking préservé.
import { usePathname } from "next/navigation";
import { useAuth } from "../AuthContext";
import { SECTIONS, findSection } from "./nav";
import OsTopbar from "./OsTopbar";
import OsSidebar from "./OsSidebar";

export default function OsShell({ children, alertsCount = 0, camsOnline = 0, camsTotal = 0 }) {
  const pathname = usePathname() || "";
  const user = useAuth();
  const section = findSection(pathname);

  return (
    <div data-os-theme={section.theme} className="min-h-screen bg-os-bg text-os-t1 font-sans">
      <OsTopbar sections={SECTIONS} activeKey={section.key} alertsCount={alertsCount} user={user} />
      <div className="flex pt-[52px]">
        <OsSidebar
          sections={SECTIONS}
          activeKey={section.key}
          activePath={pathname}
          alertsCount={alertsCount}
        />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}

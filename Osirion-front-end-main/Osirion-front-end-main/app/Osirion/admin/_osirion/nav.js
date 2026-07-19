// Architecture de navigation Osirion : topbar 3 sections → sidebar contextuelle.
// Chaque section porte son thème (Surveiller = sombre, Analyser/Configurer = clair).
import {
  Gauge, LayoutGrid, Bell, BarChart3, ListOrdered, FileText,
  Shapes, SlidersHorizontal, Video, Server,
} from "lucide-react";

export const SECTIONS = [
  {
    key: "surveiller", label: "Surveiller", theme: "dark",
    kicker: "Temps réel", title: "Supervision",
    screens: [
      { label: "Cockpit", href: "/Osirion/admin/cockpit", icon: Gauge },
      { label: "Mur de caméras", href: "/Osirion/admin/live", icon: LayoutGrid },
      { label: "Centre d'alertes", href: "/Osirion/admin/alerts", icon: Bell, badge: "alerts" },
    ],
  },
  {
    key: "analyser", label: "Analyser", theme: "light",
    kicker: "Tendances", title: "Intelligence",
    screens: [
      { label: "Analytique", href: "/Osirion/admin/analytics", icon: BarChart3 },
      { label: "Événements", href: "/Osirion/admin/events", icon: ListOrdered },
      { label: "Rapports", href: "/Osirion/admin/reports", icon: FileText },
    ],
  },
  {
    key: "configurer", label: "Configurer", theme: "light",
    kicker: "Paramétrage", title: "Administration",
    screens: [
      { label: "Zones & comptage", href: "/Osirion/admin/zones", icon: Shapes },
      { label: "Règles & alertes", href: "/Osirion/admin/rules", icon: SlidersHorizontal },
      { label: "Caméras & site", href: "/Osirion/admin/site", icon: Video },
      { label: "Système & accès", href: "/Osirion/admin/system-status", icon: Server },
    ],
    // Routes rattachées à la section (thème + surbrillance de l'item parent) mais
    // NON affichées comme items de sidebar : pages de gestion atteintes via « Gérer ».
    extra: [
      { href: "/Osirion/admin/cameras", parent: "/Osirion/admin/site" },
      { href: "/Osirion/admin/map", parent: "/Osirion/admin/site" },
      { href: "/Osirion/admin/cameras-health", parent: "/Osirion/admin/site" },
      { href: "/Osirion/admin/users", parent: "/Osirion/admin/system-status" },
      { href: "/Osirion/admin/audit", parent: "/Osirion/admin/system-status" },
      { href: "/Osirion/admin/settings", parent: "/Osirion/admin/system-status" },
      { href: "/Osirion/admin/groups", parent: "/Osirion/admin/site" },
    ],
  },
];

// Section active déduite du chemin courant (préserve le deep-linking Next.js).
export function findSection(pathname) {
  for (const s of SECTIONS) {
    if (s.screens.some((sc) => pathname === sc.href || pathname.startsWith(sc.href + "/"))) return s;
    if ((s.extra || []).some((e) => pathname === e.href || pathname.startsWith(e.href + "/"))) return s;
  }
  return SECTIONS[0];
}

// href de l'item de sidebar à surligner pour un chemin (une route « extra »
// surligne son parent). Utilisé par OsSidebar.
export function activeScreenHref(section, pathname) {
  const direct = section.screens.find((sc) => pathname === sc.href || pathname.startsWith(sc.href + "/"));
  if (direct) return direct.href;
  const ex = (section.extra || []).find((e) => pathname === e.href || pathname.startsWith(e.href + "/"));
  return ex ? ex.parent : null;
}

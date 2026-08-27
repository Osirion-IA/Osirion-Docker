// Architecture de navigation Osirion : topbar (sections + thème) + sidebar en
// ACCORDÉON qui liste TOUS les écrans, groupés par section. Chaque section porte
// son thème (Surveiller = sombre, autres = clair).
import {
  Gauge, LayoutGrid, Bell, BarChart3, ListOrdered, FileText,
  Shapes, SlidersHorizontal, Video, Layers, Activity,
  History, Server, Users, ScrollText, Settings, Info,
  UserRoundCheck,
} from "lucide-react";

export const SECTIONS = [
  {
    key: "surveiller", label: "Surveiller", theme: "light",
    kicker: "Temps réel", title: "Supervision",
    screens: [
      { label: "Cockpit", href: "/Osirion/admin/cockpit", icon: Gauge },
      { label: "Présence agents", href: "/Osirion/admin/presence", icon: UserRoundCheck },
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
    kicker: "Paramétrage", title: "Configuration",
    screens: [
      { label: "Zones & comptage", href: "/Osirion/admin/zones", icon: Shapes },
      { label: "Règles & alertes", href: "/Osirion/admin/rules", icon: SlidersHorizontal },
      { label: "Caméras", href: "/Osirion/admin/cameras", icon: Video },
      { label: "Groupes", href: "/Osirion/admin/groups", icon: Layers },
      { label: "Santé caméras", href: "/Osirion/admin/cameras-health", icon: Activity },
      { label: "Historique caméras", href: "/Osirion/admin/camera-history", icon: History },
    ],
  },
  {
    key: "systeme", label: "Système", theme: "light",
    kicker: "Administration", title: "Système & accès",
    screens: [
      { label: "État système", href: "/Osirion/admin/system-status", icon: Server },
      { label: "Utilisateurs", href: "/Osirion/admin/users", icon: Users },
      { label: "Audit", href: "/Osirion/admin/audit", icon: ScrollText },
      { label: "Paramètres", href: "/Osirion/admin/settings", icon: Settings },
      { label: "À propos", href: "/Osirion/admin/about", icon: Info },
    ],
  },
];

// Section active déduite du chemin courant (préserve le deep-linking Next.js).
export function findSection(pathname) {
  for (const s of SECTIONS) {
    if (s.screens.some((sc) => pathname === sc.href || pathname.startsWith(sc.href + "/"))) return s;
  }
  return SECTIONS[0];
}

// href de l'écran à surligner pour un chemin donné (dans une section).
export function activeScreenHref(section, pathname) {
  const direct = section.screens.find((sc) => pathname === sc.href || pathname.startsWith(sc.href + "/"));
  return direct ? direct.href : null;
}

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";

export default function AdminSidebar({
  currentRole,
  isCollapsed,
  onToggle,
  currentPath = "/",
}) {
  const menuItems = [
    {
      label: "Vue d'ensemble",
      href: "/Osirion/admin",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18h8v6h-8V3z" />
        </svg>
      ),
    },
    {
      label: "Caméras",
      href: "/Osirion/admin/cameras",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <rect x="4" y="7" width="16" height="10" rx="1.5" />
          <path d="m8 7 2-3h4l2 3" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      ),
    },
    {
      label: "Santé caméras",
      href: "/Osirion/admin/cameras-health",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      ),
    },
    {
      label: "Groupes de caméras",
      href: "/Osirion/admin/groups",
      roles: ["admin", "user"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      ),
    },
    {
      label: "Carte",
      href: "/Osirion/admin/map",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2-6-2z" />
          <path d="M9 4v14M15 6v14" />
        </svg>
      ),
    },
    {
      label: "Live streamings",
      href: "/Osirion/admin/live",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <rect x="4" y="6" width="16" height="12" rx="1.5" />
          <path d="m10 9 5 3-5 3z" />
        </svg>
      ),
    },
    {
      label: "Plaques",
      href: "/Osirion/admin/plates",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <rect x="2" y="6" width="20" height="12" rx="2" />
          <path d="M6 10v4M10 10v4M14 10v4M18 10v4" />
        </svg>
      ),
    },
    {
      label: "Blacklist",
      href: "/Osirion/admin/blacklist",
      roles: ["admin", "user"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <circle cx="12" cy="12" r="9" />
          <path d="m7.5 7.5 9 9" />
        </svg>
      ),
    },
    {
      label: "Utilisateurs & rôles",
      href: "/Osirion/admin/users",
      roles: ["admin"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M16.5 9.5a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z" />
          <path d="M4 20.5a8.5 8.5 0 0 1 16 0" />
        </svg>
      ),
    },
    {
      label: "Événements",
      href: "/Osirion/admin/events",
      roles: ["admin", "user", "viewer"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M3 12h4l2 5 4-12 2 7h6" />
        </svg>
      ),
    },
    {
      label: "Rapports",
      href: "/Osirion/admin/reports",
      roles: ["admin", "user"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M6 3h9l4 4v14H6z" />
          <path d="M9 10h6M9 14h6M9 18h3" />
        </svg>
      ),
    },
    {
      label: "Alertes",
      href: "/Osirion/admin/alerts",
      roles: ["admin", "user"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M12 2v8l4 2" />
          <circle cx="12" cy="13" r="9" />
        </svg>
      ),
    },
    {
      label: "Paramètres",
      href: "/Osirion/admin/settings",
      roles: ["admin"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <circle cx="12" cy="12" r="3.5" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
    },
    {
      label: "Audit & Maintenance",
      href: "/Osirion/admin/audit",
      roles: ["admin"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
          <path d="m9 14 2 2 4-4" />
        </svg>
      ),
    },
    {
      label: "État du système",
      href: "/Osirion/admin/system-status",
      roles: ["admin", "user"],
      icon: (
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8" />
          <path d="M12 17v4" />
          <path d="M7 8h.01M12 8h.01M17 8h.01M7 12h10" />
        </svg>
      ),
    },
  ];

  const visibleItems = menuItems.filter((item) => item.roles.includes(currentRole));

  // Gestion des tooltips en mode collapsed
  const [activeTooltip, setActiveTooltip] = useState(null);
  const timeoutRef = useRef(null);

  const showTooltip = (label) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setActiveTooltip(label);
  };

  const hideTooltip = () => {
    timeoutRef.current = setTimeout(() => setActiveTooltip(null), 120);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <aside
      className={`
        hidden lg:flex fixed left-0 top-0 h-screen flex-col
        border-r border-gray-200/70 dark:border-gray-800/60
        bg-gradient-to-b from-gray-50/95 via-white/90 to-white/80
        dark:from-gray-950/95 dark:via-gray-900/90 dark:to-gray-900/80
        backdrop-blur-lg transition-all duration-400 ease-out
        ${isCollapsed ? "w-20" : "w-72 xl:w-80"}
      `}
    >
      {/* Header */}
      <div className="shrink-0 px-5 pt-6 pb-5 flex items-start justify-between">
        {!isCollapsed ? (
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-300/60 dark:border-gray-700/50 text-[10px] font-semibold tracking-wider uppercase text-gray-700/90 dark:text-gray-300/90">
              Osirion Admin
            </div>
            <h2 className="mt-5 text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
              Supervision
            </h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Sécurité • Analytics
            </p>
          </div>
        ) : (
          <div className="text-xl font-bold tracking-wider text-gray-800/90 dark:text-gray-200/90 mx-auto mt-1">
            OA
          </div>
        )}

        <button
          onClick={onToggle}
          className="p-2.5 -mr-2 rounded-xl hover:bg-gray-200/70 dark:hover:bg-gray-800/50 transition-colors"
          aria-label={isCollapsed ? "Étendre la barre latérale" : "Réduire la barre latérale"}
        >
          <svg
            className={`h-5 w-5 transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
      </div>

      {/* Navigation avec scrollbar douce */}
      <nav
        className={`
          flex-1 px-4 py-1 overflow-y-auto
          scrollbar-soft
          scrollbar-gutter-stable
          max-h-[calc(100vh-320px)]
        `}
      >
        {visibleItems.map((item) => {
          const isActive = currentPath === item.href;
          const showBadge = !isCollapsed && item.badge !== undefined;

          return (
            <div
              key={item.label}
              className="relative"
              onMouseEnter={() => isCollapsed && showTooltip(item.label)}
              onMouseLeave={hideTooltip}
            >
              <Link
                href={item.href}
                className={`
                  group flex items-center gap-3.5 rounded-xl px-4 py-2.5 text-sm font-medium
                  transition-all duration-200 ease-out
                  ${
                    isActive
                      ? "bg-gradient-to-r from-gray-900/95 to-gray-800/90 text-white shadow-md"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-200/70 dark:hover:bg-gray-800/45 active:scale-[0.98]"
                  }
                `}
              >
                <span
                  className={`
                    flex items-center justify-center shrink-0 w-6
                    ${isActive ? "text-white" : "text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-200"}
                  `}
                >
                  {item.icon}
                </span>

                {!isCollapsed && <span className="truncate">{item.label}</span>}

                {showBadge && (
                  <span
                    className={`
                      ml-auto text-[10px] font-medium px-2.5 py-0.5 rounded-full
                      ${item.badgeColor || "bg-gray-600/80 text-white"}
                      shadow-sm
                    `}
                  >
                    {item.badge}
                  </span>
                )}
              </Link>

              {/* Tooltip quand collapsed */}
              {isCollapsed && activeTooltip === item.label && (
                <div
                  className="
                    absolute left-full ml-4 top-1/2 -translate-y-1/2
                    px-3.5 py-2 bg-gray-950/95 text-white text-sm rounded-lg
                    shadow-2xl whitespace-nowrap z-50 pointer-events-none
                    border border-gray-800/60
                    animate-fade-in
                  "
                >
                  {item.label}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Footer status (visible uniquement quand non repliée) */}
      {!isCollapsed && (
        <div className="shrink-0 px-5 pb-6 pt-4 mt-auto border-t border-gray-200/60 dark:border-gray-800/50">
          <div className="rounded-2xl bg-white/60 dark:bg-gray-900/40 p-4 border border-gray-200/70 dark:border-gray-800/50">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Centre opérationnel
            </p>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                Opérationnel
              </span>
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                96%
              </span>
            </div>
            <div className="mt-2.5 h-1.5 bg-gray-200/70 dark:bg-gray-800/50 rounded-full overflow-hidden">
              <div className="h-full w-5/6 bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full" />
            </div>
            <p className="mt-2.5 text-[11px] text-gray-500 dark:text-gray-400">
              Dernier incident : il y a 18 jours
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}
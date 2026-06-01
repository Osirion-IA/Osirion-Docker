"use client";

import { useTheme } from "../../ThemeProvider";
import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";

export default function AdminTopBar({
  title = "Tableau de bord",
  subtitle,
  showSearch = true,
  searchPlaceholder = "Rechercher...",
  actions,
}) {
  const [mounted, setMounted] = useState(false);
  const { theme, setTheme } = useTheme();
  const user = useAuth();

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="sticky top-0 z-10 backdrop-blur-xl bg-white/70 dark:bg-gray-900/70 border-b border-gray-200/70 dark:border-gray-800/60">
      <div className="px-6 lg:px-10 py-5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              {title}
            </h1>
            {subtitle && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {subtitle}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Search Bar */}
            {showSearch && (
              <div className="relative">
                <svg
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  type="search"
                  placeholder={searchPlaceholder}
                  className="w-64 max-w-full pl-10 pr-4 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:text-white transition-all"
                />
              </div>
            )}

            {/* Theme Toggle */}
            <button
              className="rounded-xl border border-gray-200 dark:border-gray-800 p-2.5 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              onClick={() =>
                setTheme((prev) =>
                  prev === "system" ? "dark" : prev === "dark" ? "light" : "system"
                )
              }
              aria-label="Changer de thème"
              title={mounted ? (theme === "system" ? "Auto" : theme === "dark" ? "Sombre" : "Clair") : "Thème"}
              suppressHydrationWarning
            >
              {!mounted ? (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              ) : theme === "system" ? (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M8 21h8M12 17v4" />
                </svg>
              ) : theme === "dark" ? (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              ) : (
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              )}
            </button>

            {/* Custom Actions */}
            {actions}

            {/* User Profile dynamique */}
            <div className="flex items-center gap-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-3 py-2">
              <span className="h-8 w-8 rounded-lg bg-gradient-to-br from-gray-800 to-gray-950 text-white flex items-center justify-center text-xs font-semibold">
                {user?.fullName ? user.fullName[0].toUpperCase() : "?"}
              </span>
              <div className="hidden lg:block">
                <p className="text-sm font-semibold leading-tight text-gray-900 dark:text-white">
                  {user?.fullName || "Utilisateur"}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {user?.role || "Role inconnu"}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {user?.email || ""}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

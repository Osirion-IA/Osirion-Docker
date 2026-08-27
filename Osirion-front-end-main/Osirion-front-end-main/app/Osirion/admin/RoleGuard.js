"use client";

import Link from "next/link";
import { useAuth } from "./AuthContext";

/**
 * Matrice des permissions par rôle.
 * Utilisée comme référence pour les guards de page et les restrictions d'action.
 */
export const ROLE_PERMISSIONS = {
  admin: {
    pages: ["dashboard", "cameras", "live", "presence", "blacklist", "users", "alerts", "settings", "system-status"],
    actions: ["view", "create", "edit", "delete", "manage-users", "manage-blacklist"],
  },
  user: {
    pages: ["dashboard", "cameras", "live", "presence", "blacklist", "alerts", "settings"],
    actions: ["view", "create", "edit", "manage-blacklist"],
  },
  viewer: {
    pages: ["dashboard", "cameras", "live", "presence"],
    actions: ["view"],
  },
};

/**
 * Hook : retourne true si le user courant possède l'une des actions listées.
 */
export function useCanDo(...actions) {
  const user = useAuth();
  if (!user) return false;
  const perms = ROLE_PERMISSIONS[user.role] ?? ROLE_PERMISSIONS.viewer;
  return actions.some((a) => perms.actions.includes(a));
}

/**
 * Composant écran d'accès refusé, à afficher à l'intérieur du <main>.
 * Exporté pour une utilisation inline dans les pages.
 */
export function AccessDenied({ role }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
      <div className="w-20 h-20 rounded-2xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center mb-6">
        <svg
          className="h-10 w-10 text-red-600 dark:text-red-400"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Accès refusé
      </h1>
      <p className="mt-3 text-sm text-gray-500 dark:text-gray-400 max-w-sm">
        Votre rôle{" "}
        <span className="font-semibold text-gray-700 dark:text-gray-300">
          ({role || "inconnu"})
        </span>{" "}
        ne vous autorise pas à consulter cette page. Contactez un administrateur si vous pensez qu'il s'agit d'une erreur.
      </p>

      <Link
        href="/Osirion/admin"
        className="mt-8 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-semibold hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m15 18-6-6 6-6" />
        </svg>
        Retour au tableau de bord
      </Link>
    </div>
  );
}

// Si user non chargé : spinner. Si rôle interdit : AccessDenied. Sinon : children.
export default function RoleGuard({ allowedRoles, children }) {
  const user = useAuth();

  // Le layout gère l'auth ; ici on attend juste que le contexte soit peuplé.
  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="h-8 w-8 rounded-full border-2 border-gray-400 dark:border-gray-600 border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!allowedRoles.includes(user.role)) {
    return <AccessDenied role={user.role} />;
  }

  return <>{children}</>;
}

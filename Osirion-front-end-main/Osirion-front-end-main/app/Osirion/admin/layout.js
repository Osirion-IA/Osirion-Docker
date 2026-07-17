"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthContext } from "./AuthContext";
import AlertNotifier from "./AlertNotifier";
import { getSetting } from "../../lib/settings";

// Lit le cookie non-httpOnly token_expires_at (timestamp ms)
function getTokenExpiry() {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)token_expires_at=([^;]*)/);
  return match ? parseInt(match[1], 10) : null;
}

export default function AdminLayout({ children }) {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  // Vérification initiale de session au montage
  useEffect(() => {
    async function verifySession() {
      try {
        let res = await fetch("/api/auth/me");

        if (res.status === 401) {
          const refresh = await fetch("/api/auth/refresh", { method: "POST" });
          if (!refresh.ok) {
            router.replace("/");
            return;
          }
          res = await fetch("/api/auth/me");
        }

        if (!res.ok) {
          router.replace("/");
          return;
        }

        const data = await res.json();
        setUser(data);
      } catch {
        router.replace("/");
      } finally {
        setChecking(false);
      }
    }

    verifySession();
  }, [router]);

  // Refresh proactif : planifie un refresh silencieux 5 min avant expiration
  // Redémarre automatiquement après chaque refresh réussi pour rester en vie
  useEffect(() => {
    if (!user) return;

    let timer = null;

    async function doRefresh() {
      const res = await fetch("/api/auth/refresh", { method: "POST" });
      if (!res.ok) {
        router.replace("/");
      } else {
        scheduleNext();
      }
    }

    function scheduleNext() {
      const expiresAt = getTokenExpiry();
      if (!expiresAt) return;

      // Rafraîchir 5 min avant l'expiration (300 000 ms)
      const delay = Math.max(0, expiresAt - Date.now() - 5 * 60 * 1000);
      timer = setTimeout(doRefresh, delay);
    }

    scheduleNext();

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [user, router]);

  // Déconnexion automatique après inactivité (paramètre Sécurité « Session (min) »).
  // Tout geste utilisateur réarme le délai ; passé ce délai sans activité, on
  // efface la session (cookies) et on redirige vers la page de connexion.
  useEffect(() => {
    if (!user) return;

    let lastActivity = Date.now();
    let loggingOut = false;

    const onActivity = () => { lastActivity = Date.now(); };
    const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"];
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));

    // Délai RELU à chaque tick → une modification du paramètre « Session (min) »
    // s'applique À CHAUD (≤ 15 s), sans rechargement, et même depuis un autre
    // onglet (localStorage partagé). Aucune dépendance au cycle de vie du layout.
    const checkId = setInterval(async () => {
      const minutes = Number(getSetting("sessionTimeout", 30)) || 30;
      const timeoutMs = minutes * 60 * 1000;
      if (loggingOut || Date.now() - lastActivity < timeoutMs) return;
      loggingOut = true;
      clearInterval(checkId);
      try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* */ }
      router.replace("/");
    }, 15000);

    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity));
      clearInterval(checkId);
    };
  }, [user, router]);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
        <p className="text-sm text-gray-500 dark:text-gray-400 animate-pulse">
          Vérification de la session...
        </p>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={user}>
      {children}
      {/* Notifications globales (toast + son) sur détection blacklist personne */}
      <AlertNotifier />
    </AuthContext.Provider>
  );
}

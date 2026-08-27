"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthContext } from "./AuthContext";
import AlertNotifier from "./AlertNotifier";
import { getSetting } from "../../lib/settings";
import { triggerRefresh } from "../../lib/fetchWithRefresh";

const LAST_ACTIVITY_KEY = "osirion-session-last-activity";
const ACTIVITY_WRITE_INTERVAL_MS = 5000;

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
      const res = await triggerRefresh();   // partagé avec fetchWithRefresh (anti-course rotation)
      if (res.ok) { scheduleNext(); return; }
      // Refresh KO : possible course (rotation / autre onglet) — vérifier la session
      // AVANT de déconnecter (le cookie a peut-être déjà été rafraîchi ailleurs).
      try {
        const me = await fetch("/api/auth/me");
        if (me.ok) { scheduleNext(); return; }
      } catch { /* */ }
      router.replace("/");
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
  // L'activité est partagée entre les onglets : un onglet ancien et inactif ne
  // doit jamais effacer les cookies pendant qu'un autre onglet est utilisé.
  useEffect(() => {
    if (!user) return;

    let lastActivity = Date.now();
    let lastSharedWrite = 0;
    let loggingOut = false;

    const readSharedActivity = () => {
      try {
        const value = Number(window.localStorage.getItem(LAST_ACTIVITY_KEY));
        return Number.isFinite(value) ? value : 0;
      } catch { return 0; }
    };
    const markActivity = (force = false) => {
      const now = Date.now();
      lastActivity = now;
      if (!force && now - lastSharedWrite < ACTIVITY_WRITE_INTERVAL_MS) return;
      lastSharedWrite = now;
      try { window.localStorage.setItem(LAST_ACTIVITY_KEY, String(now)); } catch { /* */ }
    };
    const onActivity = () => markActivity();
    const onSharedActivity = (event) => {
      if (event.key !== LAST_ACTIVITY_KEY) return;
      const value = Number(event.newValue);
      if (Number.isFinite(value)) lastActivity = Math.max(lastActivity, value);
    };
    const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"];
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    window.addEventListener("storage", onSharedActivity);
    markActivity(true);

    // Délai RELU à chaque tick → une modification du paramètre « Session (min) »
    // s'applique À CHAUD (≤ 15 s), sans rechargement, et même depuis un autre
    // onglet (localStorage partagé). Aucune dépendance au cycle de vie du layout.
    // Une vidéo EN LECTURE compte comme une activité : sur une plateforme de
    // vidéosurveillance, regarder le mur de caméras (sans souris/clavier) n'est PAS
    // de l'inactivité — sinon on serait déconnecté en pleine surveillance.
    const isWatchingLive = () => {
      for (const v of document.querySelectorAll("video")) {
        if (!v.paused && !v.ended && v.readyState >= 2 && v.currentTime > 0) return true;
      }
      return false;
    };

    const checkId = setInterval(async () => {
      const raw = getSetting("sessionTimeout", 30);
      const minutes = Number.isFinite(Number(raw)) ? Number(raw) : 30;
      if (minutes <= 0) return;                                     // 0 = déconnexion auto désactivée
      if (isWatchingLive()) { markActivity(); return; }             // visionnage live = activité
      const effectiveActivity = Math.max(lastActivity, readSharedActivity());
      if (loggingOut || Date.now() - effectiveActivity < minutes * 60 * 1000) return;
      loggingOut = true;
      clearInterval(checkId);
      try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* */ }
      router.replace("/");
    }, 15000);

    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity));
      window.removeEventListener("storage", onSharedActivity);
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

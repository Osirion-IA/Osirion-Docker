"use client";

import { useState, useEffect } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { Settings, Shield, Target, AlertTriangle, CheckCircle2, Save, RotateCcw, User } from "lucide-react";
import { CORE_URL } from "../../../lib/publicUrls";

// Paramètres persistés localement (Général + Sécurité). On NE persiste PAS ici
// les toggles de Détection : le Core en est la source de vérité (lus/poussés via
// /api/face et /api/unknown-face, appliqués à chaud).
const SETTINGS_STORAGE_KEY = "osirion-settings";
const PERSIST_KEYS = ["siteName", "sessionTimeout", "passwordMinLength"];

export default function SettingsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState("general");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  // Seuls les paramètres ayant un effet réel sur le système sont conservés.
  const [settings, setSettings] = useState({
    siteName: "Osirion Surveillance",   // → titre de l'onglet navigateur
    sessionTimeout: 30,                 // → déconnexion auto après inactivité
    passwordMinLength: 8,               // → création d'utilisateur (longueur min)
    faceRecognition: true,              // → Core (pipeline facial), à chaud — DÉFAUT activé
    unknownFaceEvent: false,            // → Core (événement visage non reconnu), à chaud
  });

  const handleSettingChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setHasUnsavedChanges(true);
  };

  // CORE_URL (API facial / visage inconnu) dérivé de l'hôte d'accès — cf. lib/publicUrls.

  // Au montage : récupérer l'état RÉEL de la reconnaissance faciale côté Core.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${CORE_URL}/api/face/status`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setSettings((prev) => ({ ...prev, faceRecognition: data.face_recognition_enabled !== false }));
      } catch {
        // Core injoignable : on garde l'état local par défaut (activé), sans bloquer.
      }
    })();
    return () => { cancelled = true; };
  }, [CORE_URL]);

  // Active/désactive le pipeline de reconnaissance faciale côté Core (à chaud).
  const toggleFace = async (enabled) => {
    try {
      const res = await fetch(`${CORE_URL}/api/face/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (res.ok) {
        const data = await res.json();
        setSettings((prev) => ({ ...prev, faceRecognition: !!data.face_recognition_enabled }));
      }
    } catch {
      console.warn("Face toggle: Core injoignable à", CORE_URL);
    }
  };

  // Au montage : récupérer l'état RÉEL de l'événement « visage non reconnu ».
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${CORE_URL}/api/unknown-face/status`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setSettings((prev) => ({ ...prev, unknownFaceEvent: !!data.unknown_face_event_enabled }));
      } catch {
        // Core injoignable : on garde l'état local par défaut, sans bloquer la page.
      }
    })();
    return () => { cancelled = true; };
  }, [CORE_URL]);

  // Active/désactive l'enregistrement d'un événement pour les visages non reconnus.
  const toggleUnknownFace = async (enabled) => {
    try {
      const res = await fetch(`${CORE_URL}/api/unknown-face/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (res.ok) {
        const data = await res.json();
        setSettings((prev) => ({ ...prev, unknownFaceEvent: !!data.unknown_face_event_enabled }));
      }
    } catch {
      console.warn("Unknown-face toggle: Core injoignable à", CORE_URL);
    }
  };

  // Au montage : restaurer les paramètres persistés (Général + Sécurité).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      const subset = {};
      for (const k of PERSIST_KEYS) if (saved[k] !== undefined) subset[k] = saved[k];
      if (Object.keys(subset).length) setSettings((prev) => ({ ...prev, ...subset }));
      if (saved.siteName) document.title = saved.siteName;   // effet visible (titre onglet)
    } catch {
      // localStorage indisponible ou JSON invalide : on garde les valeurs par défaut.
    }
  }, []);

  const handleSave = () => {
    try {
      const payload = {};
      for (const k of PERSIST_KEYS) payload[k] = settings[k];
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(payload));
      if (settings.siteName) document.title = settings.siteName;
    } catch {
      // Persistance impossible : on ne bloque pas l'interface.
    }
    setHasUnsavedChanges(false);
    setSavedMsg(true);
    setTimeout(() => setSavedMsg(false), 2500);
  };

  const handleReset = () => {
    // Restaure les champs persistés sur la dernière valeur enregistrée
    // (ou les défauts si rien n'a encore été sauvegardé).
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      const saved = raw ? JSON.parse(raw) : {};
      setSettings((prev) => {
        const next = { ...prev };
        for (const k of PERSIST_KEYS) if (saved[k] !== undefined) next[k] = saved[k];
        return next;
      });
    } catch {
      // ignore
    }
    setHasUnsavedChanges(false);
  };

  const tabs = [
    { id: "general", label: "Général", icon: <Settings className="h-4 w-4" /> },
    { id: "security", label: "Sécurité", icon: <Shield className="h-4 w-4" /> },
    { id: "detection", label: "Détection", icon: <Target className="h-4 w-4" /> },
  ];

  if (user && !["admin"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/settings" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/settings"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Paramètres"
            subtitle="Configuration du système Osirion"
            showSearch={false}
            actions={
              <>
                {hasUnsavedChanges && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-sm font-medium">
                    <div className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
                    Modifications non sauvegardées
                  </div>
                )}

                {savedMsg && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-sm font-medium">
                    <CheckCircle2 className="h-4 w-4" />
                    Paramètres enregistrés
                  </div>
                )}

                <button
                  onClick={handleReset}
                  className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2">
                  <RotateCcw className="h-4 w-4" />
                  Réinitialiser
                </button>

                <button
                  onClick={handleSave}
                  disabled={!hasUnsavedChanges}
                  className={`rounded-xl px-4 py-2.5 text-sm font-medium transition-all flex items-center gap-2 ${
                    hasUnsavedChanges
                      ? "bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 text-white dark:text-gray-900 shadow-lg"
                      : "bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed"
                  }`}>
                  <Save className="h-4 w-4" />
                  Enregistrer
                </button>
              </>
            }
          />

          <div className="px-6 lg:px-10 py-6">
            {/* Onglets */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-2 mb-6">
              <div className="flex gap-2 overflow-x-auto">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${
                      activeTab === tab.id
                        ? "bg-gray-900 dark:bg-white text-white dark:text-gray-900 shadow"
                        : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* ── Général ── */}
            {activeTab === "general" && (
              <div className="space-y-6">
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white">
                      <Settings className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white">Paramètres généraux</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Configuration de base du système</p>
                    </div>
                  </div>

                  <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      Nom du site
                    </label>
                    <input
                      type="text"
                      value={settings.siteName}
                      onChange={(e) => handleSettingChange("siteName", e.target.value)}
                      className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-medium"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                      Affiché comme titre de l&apos;onglet du navigateur (appliqué à l&apos;enregistrement).
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ── Sécurité ── */}
            {activeTab === "security" && (
              <div className="space-y-6">
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center text-white">
                      <Shield className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white">Sécurité et authentification</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Protection et contrôle d&apos;accès</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                      <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                        Session (min)
                      </label>
                      <input
                        type="number"
                        value={settings.sessionTimeout}
                        onChange={(e) => handleSettingChange("sessionTimeout", parseInt(e.target.value))}
                        className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold"
                        min="1"
                        max="120"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                        Déconnexion automatique après inactivité (appliqué à chaud, ≤ 15 s).
                      </p>
                    </div>

                    <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                      <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                        Mot de passe (min)
                      </label>
                      <input
                        type="number"
                        value={settings.passwordMinLength}
                        onChange={(e) => handleSettingChange("passwordMinLength", parseInt(e.target.value))}
                        className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold"
                        min="6"
                        max="32"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                        Longueur minimale exigée à la création d&apos;un utilisateur.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── Détection (toggles appliqués à chaud côté Core) ── */}
            {activeTab === "detection" && (
              <div className="space-y-6">
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center text-white">
                      <Target className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white">Détection</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400">Modules activables à chaud (moteur Core)</p>
                    </div>
                  </div>

                  <div className="space-y-4">
                    {/* Reconnaissance faciale (pipeline principal, à chaud) */}
                    <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                          <User className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="text-sm font-bold text-gray-900 dark:text-white">Reconnaissance faciale</div>
                          <div className="text-xs text-gray-600 dark:text-gray-400">Détecter et identifier les visages (pipeline principal)</div>
                          {settings.faceRecognition === false && (
                            <div className="text-[11px] mt-1 text-amber-600 dark:text-amber-400">
                              ⚠ Module suspendu — aucun visage détecté ni reconnu
                            </div>
                          )}
                        </div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={settings.faceRecognition}
                          onChange={(e) => {
                            setSettings((p) => ({ ...p, faceRecognition: e.target.checked }));
                            toggleFace(e.target.checked);
                          }}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                      </label>
                    </div>


                    {/* Visages non reconnus */}
                    <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                          <AlertTriangle className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="text-sm font-bold text-gray-900 dark:text-white">Visages non reconnus</div>
                          <div className="text-xs text-gray-600 dark:text-gray-400">Enregistrer un événement distinct (UNKNOWN_FACE) quand un visage est détecté mais non identifié</div>
                        </div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={settings.unknownFaceEvent}
                          onChange={(e) => {
                            setSettings((p) => ({ ...p, unknownFaceEvent: e.target.checked }));
                            toggleUnknownFace(e.target.checked);
                          }}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-rose-300 dark:peer-focus:ring-rose-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-rose-600"></div>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import {
  Settings, Globe, Languages, Calendar, Shield, Lock, 
  Bell, Mail, Smartphone, AlertCircle, AlertTriangle, 
  Info, Video, Gauge, HardDrive, Target, User, 
  Package, Car, Zap, Activity, Key, Webhook, 
  Search, ChevronRight, Clock, CheckCircle2, Save, RotateCcw
} from "lucide-react";

export default function SettingsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState("general");
  const [searchQuery, setSearchQuery] = useState("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState({});

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  // États des paramètres
  const [settings, setSettings] = useState({
    // Général
    siteName: "Osirion Surveillance",
    timezone: "Europe/Paris",
    language: "fr",
    dateFormat: "DD/MM/YYYY",
    
    // Sécurité
    sessionTimeout: 30,
    passwordMinLength: 8,
    twoFactorAuth: true,
    loginAttempts: 3,
    
    // Notifications
    emailNotifications: true,
    pushNotifications: true,
    alertCritical: true,
    alertWarning: true,
    alertInfo: false,
    
    // Caméras
    defaultResolution: "1080p",
    defaultFps: 25,
    recordingRetention: 30,
    motionDetection: true,
    
    // Détection
    confidenceThreshold: 0.75,
    faceRecognition: true,
    objectDetection: true,
    licencePlateRecognition: true,
    
    // API
    apiEnabled: true,
    apiRateLimit: 1000,
    webhookEnabled: true,
    webhookUrl: "https://api.example.com/webhooks/osirion",
  });

  const handleSettingChange = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
    setHasUnsavedChanges(true);
  };

  const handleSave = () => {
    // Logique de sauvegarde
    setHasUnsavedChanges(false);
    // Afficher une notification de succès
  };

  const handleReset = () => {
    // Logique de réinitialisation
    setHasUnsavedChanges(false);
  };

  const toggleAdvanced = (section) => {
    setShowAdvanced(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const tabs = [
    { id: "general", label: "Général", icon: <Settings className="h-4 w-4" /> },
    { id: "security", label: "Sécurité", icon: <Shield className="h-4 w-4" /> },
    { id: "notifications", label: "Notifications", icon: <Bell className="h-4 w-4" /> },
    { id: "cameras", label: "Caméras", icon: <Video className="h-4 w-4" /> },
    { id: "detection", label: "Détection", icon: <Target className="h-4 w-4" /> },
    { id: "api", label: "API & Webhooks", icon: <Activity className="h-4 w-4" /> },
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
            searchPlaceholder="Rechercher un paramètre..."
            showSearch={false}
            actions={
              <>
                {hasUnsavedChanges && (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-sm font-medium">
                    <div className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
                    Modifications non sauvegardées
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
                      ? 'bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 text-white dark:text-gray-900 shadow-lg'
                      : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                  }`}>
                  <Save className="h-4 w-4" />
                  Enregistrer
                </button>
              </>
            }
          />

          <div className="px-6 lg:px-10 py-6">
            {/* Barre de recherche */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-4 mb-6">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                <input
                  type="text"
                  placeholder="Rechercher un paramètre..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-600 text-sm"
                />
              </div>
            </div>

            {/* Onglets */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-2 mb-6">
              <div className="flex gap-2 overflow-x-auto">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap ${
                      activeTab === tab.id
                        ? "bg-gray-900 dark:bg-white text-white dark:text-gray-900 shadow-lg"
                        : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                    }`}
                  >
                    <span>{tab.icon}</span>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Contenu des onglets */}
            <div className="space-y-6">
              {/* Général */}
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
                    
                    <div className="space-y-5">
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
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Ce nom apparaîtra dans l'interface et les emails</p>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                            <svg className="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="10" />
                              <path d="M12 6v6l4 2" />
                            </svg>
                            Fuseau horaire
                          </label>
                          <select
                            value={settings.timezone}
                            onChange={(e) => handleSettingChange("timezone", e.target.value)}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                          >
                            <option value="Europe/Paris">🇫🇷 Europe/Paris (GMT+1)</option>
                            <option value="Europe/London">🇬🇧 Europe/London (GMT+0)</option>
                            <option value="America/New_York">🇺🇸 America/New York (GMT-5)</option>
                            <option value="Asia/Tokyo">🇯🇵 Asia/Tokyo (GMT+9)</option>
                          </select>
                        </div>

                        <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                            <svg className="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                              <circle cx="12" cy="10" r="3" />
                            </svg>
                            Langue
                          </label>
                          <select
                            value={settings.language}
                            onChange={(e) => handleSettingChange("language", e.target.value)}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                          >
                            <option value="fr">🇫🇷 Français</option>
                            <option value="en">🇬🇧 English</option>
                            <option value="es">🇪🇸 Español</option>
                            <option value="de">🇩🇪 Deutsch</option>
                          </select>
                        </div>
                      </div>

                      <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                          <svg className="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                            <line x1="16" y1="2" x2="16" y2="6" />
                            <line x1="8" y1="2" x2="8" y2="6" />
                            <line x1="3" y1="10" x2="21" y2="10" />
                          </svg>
                          Format de date
                        </label>
                        <select
                          value={settings.dateFormat}
                          onChange={(e) => handleSettingChange("dateFormat", e.target.value)}
                          className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                          <option value="DD/MM/YYYY">DD/MM/YYYY (08/02/2026)</option>
                          <option value="MM/DD/YYYY">MM/DD/YYYY (02/08/2026)</option>
                          <option value="YYYY-MM-DD">YYYY-MM-DD (2026-02-08)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Sécurité */}
              {activeTab === "security" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-red-500 to-red-600 flex items-center justify-center text-white">
                        <Shield className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">Sécurité et authentification</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Protection et contrôle d'accès</p>
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                            Session (min)
                          </label>
                          <input
                            type="number"
                            value={settings.sessionTimeout}
                            onChange={(e) => handleSettingChange("sessionTimeout", parseInt(e.target.value))}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold"
                            min="5"
                            max="120"
                          />
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Déconnexion auto après inactivité</p>
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
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Caractères minimum requis</p>
                        </div>

                        <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                            Tentatives max
                          </label>
                          <input
                            type="number"
                            value={settings.loginAttempts}
                            onChange={(e) => handleSettingChange("loginAttempts", parseInt(e.target.value))}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold"
                            min="1"
                            max="10"
                          />
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Avant blocage du compte</p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 rounded-xl bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                            <Lock className="h-6 w-6" />
                          </div>
                          <div>
                            <div className="text-base font-bold text-gray-900 dark:text-white">Authentification à deux facteurs (2FA)</div>
                            <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                              Sécurité renforcée avec code SMS ou application
                            </div>
                          </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={settings.twoFactorAuth}
                            onChange={(e) => handleSettingChange("twoFactorAuth", e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="w-14 h-7 bg-gray-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 dark:peer-focus:ring-green-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all dark:border-gray-600 peer-checked:bg-green-600"></div>
                        </label>
                      </div>

                      {/* Section avancée */}
                      <div className="mt-6">
                        <button
                          onClick={() => toggleAdvanced('security')}
                          className="flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                        >
                          <ChevronRight className={`h-4 w-4 transition-transform ${showAdvanced.security ? 'rotate-90' : ''}`} />
                          Options avancées
                        </button>

                        {showAdvanced.security && (
                          <div className="mt-4 space-y-3 pl-6 border-l-2 border-gray-200 dark:border-gray-700">
                            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                              <div className="flex items-center justify-between">
                                <div>
                                  <div className="text-sm font-medium text-gray-900 dark:text-white">Forcer HTTPS</div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Redirection automatique vers connexion sécurisée</div>
                                </div>
                                <label className="relative inline-flex items-center cursor-pointer">
                                  <input type="checkbox" defaultChecked className="sr-only peer" />
                                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                                </label>
                              </div>
                            </div>

                            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                              <div className="flex items-center justify-between">
                                <div>
                                  <div className="text-sm font-medium text-gray-900 dark:text-white">Log des connexions</div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Enregistrer toutes les tentatives de connexion</div>
                                </div>
                                <label className="relative inline-flex items-center cursor-pointer">
                                  <input type="checkbox" defaultChecked className="sr-only peer" />
                                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                                </label>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Notifications */}
              {activeTab === "notifications" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-yellow-500 to-orange-500 flex items-center justify-center text-white">
                        <Bell className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">Notifications</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Gérer les alertes et communications</p>
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      {/* Canaux de notification */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <Mail className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900 dark:text-white">Email</div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Alertes par email</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.emailNotifications}
                              onChange={(e) => handleSettingChange("emailNotifications", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                          </label>
                        </div>

                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <Smartphone className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900 dark:text-white">Push</div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Temps réel</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.pushNotifications}
                              onChange={(e) => handleSettingChange("pushNotifications", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                          </label>
                        </div>
                      </div>

                      {/* Types d'alertes */}
                      <div className="mt-6">
                        <label className="flex items-center gap-2 text-sm font-bold text-gray-700 dark:text-gray-300 mb-3">
                          <Target className="h-4 w-4" /> Types d'alertes à notifier
                        </label>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <label className="flex items-center gap-3 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                            <input
                              type="checkbox"
                              checked={settings.alertCritical}
                              onChange={(e) => handleSettingChange("alertCritical", e.target.checked)}
                              className="h-5 w-5 text-gray-600 border-gray-300 rounded focus:ring-gray-500"
                            />
                            <div>
                              <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                <AlertCircle className="h-4 w-4 text-red-500" /> Critiques
                              </div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Haute priorité</div>
                            </div>
                          </label>
                          
                          <label className="flex items-center gap-3 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                            <input
                              type="checkbox"
                              checked={settings.alertWarning}
                              onChange={(e) => handleSettingChange("alertWarning", e.target.checked)}
                              className="h-5 w-5 text-gray-600 border-gray-300 rounded focus:ring-gray-500"
                            />
                            <div>
                              <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                <AlertTriangle className="h-4 w-4 text-yellow-600" /> Avertissements
                              </div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Priorité moyenne</div>
                            </div>
                          </label>
                          
                          <label className="flex items-center gap-3 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                            <input
                              type="checkbox"
                              checked={settings.alertInfo}
                              onChange={(e) => handleSettingChange("alertInfo", e.target.checked)}
                              className="h-5 w-5 text-gray-600 border-gray-300 rounded focus:ring-gray-500"
                            />
                            <div>
                              <div className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-white">
                                <Info className="h-4 w-4 text-blue-500" /> Informations
                              </div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Basse priorité</div>
                            </div>
                          </label>
                        </div>
                      </div>

                      {/* Options avancées */}
                      <div className="mt-6">
                        <button
                          onClick={() => toggleAdvanced('notifications')}
                          className="flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                        >
                          <ChevronRight className={`h-4 w-4 transition-transform ${showAdvanced.notifications ? 'rotate-90' : ''}`} />
                          Planification et filtres
                        </button>

                        {showAdvanced.notifications && (
                          <div className="mt-4 space-y-3 pl-6 border-l-2 border-gray-200 dark:border-gray-700">
                            <div className="p-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                              <label className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white mb-2">
                                <Clock className="h-4 w-4" /> Mode silencieux (heures)
                              </label>
                              <div className="grid grid-cols-2 gap-2">
                                <input type="time" defaultValue="22:00" className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm" />
                                <input type="time" defaultValue="08:00" className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm" />
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Désactiver les notifications entre ces heures</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Caméras */}
              {activeTab === "cameras" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Paramètres des caméras</h3>
                    
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-2">
                            <Gauge className="h-4 w-4" /> Résolution par défaut
                          </label>
                          <select
                            value={settings.defaultResolution}
                            onChange={(e) => handleSettingChange("defaultResolution", e.target.value)}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-medium"
                          >
                            <option value="720p">HD 720p (1280x720)</option>
                            <option value="1080p">Full HD 1080p (1920x1080)</option>
                            <option value="2k">2K (2560x1440)</option>
                            <option value="4k">4K UHD (3840x2160)</option>
                          </select>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Qualité vidéo pour nouvelles caméras</p>
                        </div>

                        <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-2">
                            <Zap className="h-4 w-4" /> Images par seconde
                          </label>
                          <select
                            value={settings.defaultFps}
                            onChange={(e) => handleSettingChange("defaultFps", parseInt(e.target.value))}
                            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-medium"
                          >
                            <option value="15">15 FPS - Standard</option>
                            <option value="25">25 FPS - PAL Europe</option>
                            <option value="30">30 FPS - NTSC USA</option>
                            <option value="60">60 FPS - Haute vitesse</option>
                          </select>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Fluidité de l'enregistrement</p>
                        </div>
                      </div>

                      <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-2">
                          <HardDrive className="h-4 w-4" /> Rétention des enregistrements
                        </label>
                        <div className="flex items-center gap-3">
                          <input
                            type="number"
                            value={settings.recordingRetention}
                            onChange={(e) => handleSettingChange("recordingRetention", parseInt(e.target.value))}
                            className="w-32 px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold text-center"
                            min="1"
                            max="365"
                          />
                          <span className="text-sm font-medium text-gray-900 dark:text-white">jours</span>
                          <div className="flex-1 text-xs text-gray-500 dark:text-gray-400">
                            ≈ {Math.round(settings.recordingRetention / 30)} mois
                          </div>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Suppression automatique des vidéos anciennes</p>
                      </div>

                      <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 rounded-xl bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                            <Target className="h-6 w-6" />
                          </div>
                          <div>
                            <div className="text-base font-bold text-gray-900 dark:text-white">Détection de mouvement</div>
                            <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Enregistrement automatique sur mouvement détecté</div>
                          </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={settings.motionDetection}
                            onChange={(e) => handleSettingChange("motionDetection", e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="w-14 h-7 bg-gray-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 dark:peer-focus:ring-emerald-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all dark:border-gray-600 peer-checked:bg-emerald-600"></div>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Détection */}
              {activeTab === "detection" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-pink-500 to-rose-600 flex items-center justify-center text-white">
                        <Target className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">Intelligence artificielle</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Configuration de la détection et reconnaissance</p>
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <div className="p-6 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-3">
                          <Activity className="h-4 w-4" /> Seuil de confiance
                        </label>
                        <div className="flex items-center gap-4">
                          <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={settings.confidenceThreshold}
                            onChange={(e) => handleSettingChange("confidenceThreshold", parseFloat(e.target.value))}
                            className="flex-1 h-3 bg-gradient-to-r from-red-400 via-yellow-400 to-green-500 rounded-lg appearance-none cursor-pointer"
                            style={{
                              background: `linear-gradient(to right, #f87171 0%, #fbbf24 50%, #34d399 100%)`
                            }}
                          />
                          <span className="text-sm font-bold text-gray-900 dark:text-white w-12 text-right">
                            {settings.confidenceThreshold.toFixed(2)}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                          Précision minimale requise pour déclencher une alerte
                        </div>
                      </div>

                      <div className="space-y-3 mt-6">
                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <User className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900 dark:text-white">Reconnaissance faciale</div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Détecter et identifier les visages</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.faceRecognition}
                              onChange={(e) => handleSettingChange("faceRecognition", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                          </label>
                        </div>

                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <Package className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900 dark:text-white">Détection d'objets</div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Identifier les objets dans le flux</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.objectDetection}
                              onChange={(e) => handleSettingChange("objectDetection", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 dark:peer-focus:ring-green-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-green-600"></div>
                          </label>
                        </div>

                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <Car className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900 dark:text-white">Plaques d'immatriculation</div>
                              <div className="text-xs text-gray-600 dark:text-gray-400">Lire et identifier les plaques</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.licencePlateRecognition}
                              onChange={(e) => handleSettingChange("licencePlateRecognition", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-orange-300 dark:peer-focus:ring-orange-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-orange-600"></div>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* API */}
              {activeTab === "api" && (
                <div className="space-y-6">
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white">
                        <Video className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">API et Webhooks</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Intégrations externes et automatisations</p>
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 rounded-xl bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                            <Activity className="h-6 w-6" />
                          </div>
                          <div>
                            <div className="text-base font-bold text-gray-900 dark:text-white">API REST activée</div>
                            <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Autoriser l'accès externe via API</div>
                          </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={settings.apiEnabled}
                            onChange={(e) => handleSettingChange("apiEnabled", e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="w-14 h-7 bg-gray-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                        </label>
                      </div>

                      {settings.apiEnabled && (
                        <div className="space-y-4 mt-4">
                          <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                            <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-2">
                              <Gauge className="h-4 w-4" /> Limite de requêtes (par heure)
                            </label>
                            <input
                              type="number"
                              value={settings.apiRateLimit}
                              onChange={(e) => handleSettingChange("apiRateLimit", parseInt(e.target.value))}
                              className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-bold"
                              min="100"
                              max="10000"
                            />
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Protection contre les abus</p>
                          </div>

                          <div className="p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                            <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-3">
                              <Key className="h-4 w-4" /> Clé API
                            </label>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 px-3 py-2 rounded-lg bg-white dark:bg-gray-900 text-xs font-mono text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-700">
                                osrn_api_1a2b3c4d5e6f7g8h9i0j
                              </code>
                              <button className="px-4 py-2.5 rounded-xl bg-gray-700 hover:bg-gray-800 dark:bg-gray-600 dark:hover:bg-gray-700 text-white font-medium text-sm transition-colors flex items-center gap-2">
                                <CheckCircle2 className="h-4 w-4" /> Copier
                              </button>
                              <button className="px-4 py-2.5 rounded-xl bg-gray-700 hover:bg-gray-800 dark:bg-gray-600 dark:hover:bg-gray-700 text-white font-medium text-sm transition-colors flex items-center gap-2">
                                <RotateCcw className="h-4 w-4" /> Régénérer
                              </button>
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Ne partagez jamais cette clé publiquement</p>
                          </div>
                        </div>
                      )}

                      <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-800">
                        <div className="flex items-center justify-between p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center gap-4">
                            <div className="h-12 w-12 rounded-xl bg-gray-700 dark:bg-gray-600 flex items-center justify-center text-white">
                              <Webhook className="h-6 w-6" />
                            </div>
                            <div>
                              <div className="text-base font-bold text-gray-900 dark:text-white">Webhooks activés</div>
                              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Notifications vers URL externe</div>
                            </div>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={settings.webhookEnabled}
                              onChange={(e) => handleSettingChange("webhookEnabled", e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-14 h-7 bg-gray-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-300 dark:peer-focus:ring-green-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all dark:border-gray-600 peer-checked:bg-green-600"></div>
                          </label>
                        </div>

                        {settings.webhookEnabled && (
                          <div className="mt-4 p-5 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700">
                            <label className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-2">
                              <Globe className="h-4 w-4" /> URL du webhook
                            </label>
                            <input
                              type="url"
                              value={settings.webhookUrl}
                              onChange={(e) => handleSettingChange("webhookUrl", e.target.value)}
                              placeholder="https://api.example.com/webhooks/osirion"
                              className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-400 dark:focus:ring-gray-600 text-sm font-mono"
                            />
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Les événements seront envoyés en POST à cette URL</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

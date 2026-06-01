"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

function SnapshotLightbox({ alert, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const src = alert.snapshot_url.startsWith("http")
    ? alert.snapshot_url
    : `/api/images?path=${encodeURIComponent(alert.snapshot_url)}`;

  const date = new Date(alert.timestamp).toLocaleString("fr-FR", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/85 backdrop-blur-sm" onClick={onClose} />

      <div className="relative flex flex-col items-center max-w-4xl w-full max-h-[90vh]">
        {/* Bouton fermer */}
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 z-10 h-9 w-9 rounded-full bg-white dark:bg-gray-800 shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        {/* Image */}
        <img
          src={src}
          alt={`Snapshot événement #${alert.id}`}
          className="max-h-[72vh] max-w-full rounded-2xl object-contain shadow-2xl"
        />

        {/* Méta-données sous l'image */}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white/10 backdrop-blur-sm border border-white/20">
          <span className="text-white/70 text-xs">#{alert.id}</span>
          <span className="text-white/30 text-xs">·</span>
          <span className="text-white text-xs font-semibold">{alert.camera_nom}</span>
          {alert.camera_location && (
            <>
              <span className="text-white/30 text-xs">·</span>
              <span className="text-white/70 text-xs">{alert.camera_location}</span>
            </>
          )}
          {alert.person_nom && (
            <>
              <span className="text-white/30 text-xs">·</span>
              <span className="text-white text-xs font-semibold">{alert.person_nom}</span>
            </>
          )}
          {alert.confidence && (
            <>
              <span className="text-white/30 text-xs">·</span>
              <span className="text-white/70 text-xs">{Math.round(alert.confidence * 100)}%</span>
            </>
          )}
          <span className="text-white/30 text-xs">·</span>
          <span className="text-white/70 text-xs">{date}</span>
        </div>
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("tous");

  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");
  const [lightboxAlert, setLightboxAlert] = useState(null);

  const user = useAuth();
  const currentRole = user?.role || "viewer";

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const res = await fetchWithRefresh("/api/events?limit=100");
      if (!res) return;
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setFetchError(d?.message || "Erreur de chargement.");
        return;
      }
      const data = await res.json();
      setAlerts(Array.isArray(data) ? data : []);
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  // Filtrer les alertes
  const filteredAlerts = useMemo(() => {
    return alerts.filter((alert) => {
      const matchesSearch =
        searchQuery === "" ||
        (alert.camera_nom || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        (alert.camera_location || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
        alert.event_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (alert.person_nom && alert.person_nom.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesEventType =
        eventTypeFilter === "tous" || alert.event_type === eventTypeFilter;

      return matchesSearch && matchesEventType;
    });
  }, [alerts, searchQuery, eventTypeFilter]);

  // Statistiques
  const stats = useMemo(() => {
    return {
      total: alerts.length,
      recognition: alerts.filter((a) => a.event_type === "recognition").length,
      blacklist: alerts.filter((a) => a.event_type === "blacklist_detected").length,
      intrusion: alerts.filter((a) => a.event_type === "intrusion").length,
      unauthorized: alerts.filter((a) => a.event_type === "unauthorized_access").length,
      critical: alerts.filter((a) => a.event_type === "blacklist_detected" || a.event_type === "intrusion").length,
    };
  }, [alerts]);

  const getEventTypeBadge = (eventType) => {
    const styles = {
      recognition: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      blacklist_detected: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      intrusion: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
      unauthorized_access: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
      suspicious_activity: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
      motion_detected: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      crowd_detected: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
      loitering: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    };

    const labels = {
      recognition: "Reconnaissance",
      blacklist_detected: "Blacklist détectée",
      intrusion: "Intrusion",
      unauthorized_access: "Accès non autorisé",
      suspicious_activity: "Activité suspecte",
      motion_detected: "Mouvement détecté",
      crowd_detected: "Foule détectée",
      loitering: "Rôdage",
    };

    const icons = {
      recognition: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      ),
      blacklist_detected: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="9" />
          <path d="m7.5 7.5 9 9" />
        </svg>
      ),
      intrusion: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M12 2v8l4 2" />
          <circle cx="12" cy="13" r="9" />
        </svg>
      ),
      unauthorized_access: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 9.9-1" />
        </svg>
      ),
      suspicious_activity: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
      motion_detected: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      ),
      crowd_detected: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      ),
      loitering: (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      ),
    };

    const style = styles[eventType] || "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
    const label = labels[eventType] || eventType;
    const icon = icons[eventType] || null;

    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${style}`}>
        {icon}
        {label}
      </span>
    );
  };

  const formatDateTime = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);

    if (minutes < 60) return `Il y a ${minutes} min`;
    if (hours < 24) return `Il y a ${hours}h`;
    return date.toLocaleDateString("fr-FR", { 
      day: "2-digit", 
      month: "short", 
      hour: "2-digit",
      minute: "2-digit" 
    });
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.9) return "text-green-600 dark:text-green-400";
    if (confidence >= 0.8) return "text-blue-600 dark:text-blue-400";
    if (confidence >= 0.7) return "text-yellow-600 dark:text-yellow-400";
    return "text-red-600 dark:text-red-400";
  };

  if (user && !["admin", "user"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/alerts" />
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
          currentPath="/Osirion/admin/alerts"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Alertes"
            subtitle={`${stats.total} alertes • ${stats.recognition} reconnaissances • ${stats.critical} critiques`}
            searchPlaceholder="Rechercher une alerte..."
            showSearch={false}
            actions={
              <>
                <button className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                  </svg>
                  Exporter
                </button>

                <button
                  onClick={loadAlerts}
                  className="rounded-xl bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 text-white dark:text-gray-900 px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <svg className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="1 4 1 10 7 10" />
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                  Actualiser
                </button>
              </>
            }
          />

          {/* Statistiques */}
          <div className="px-6 lg:px-10 py-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Total</p>
                    <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">{stats.total}</p>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                    <svg className="h-6 w-6 text-gray-600 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v8l4 2" />
                      <circle cx="12" cy="13" r="9" />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Reconnaissances</p>
                    <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">{stats.recognition}</p>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <svg className="h-6 w-6 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Critiques</p>
                    <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-2">{stats.critical}</p>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <svg className="h-6 w-6 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Intrusions</p>
                    <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">{stats.intrusion}</p>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
                    <svg className="h-6 w-6 text-orange-600 dark:text-orange-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="11" width="18" height="11" rx="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            {/* Filtres et Recherche */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-4 mb-6">
              <div className="flex flex-col lg:flex-row gap-4">
                {/* Barre de recherche */}
                <div className="flex-1">
                  <div className="relative">
                    <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="11" cy="11" r="8" />
                      <path d="m21 21-4.35-4.35" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Rechercher une alerte..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-600 text-sm"
                    />
                  </div>
                </div>

                {/* Filtre par type d'événement */}
                <div className="flex gap-2 flex-wrap">
                  {[
                    { label: "Tous", value: "tous" },
                    { label: "Reconnaissance", value: "recognition" },
                    { label: "Blacklist", value: "blacklist_detected" },
                    { label: "Intrusion", value: "intrusion" },
                    { label: "Accès non autorisé", value: "unauthorized_access" },
                    { label: "Suspect", value: "suspicious_activity" },
                  ].map((filter) => (
                    <button
                      key={filter.value}
                      onClick={() => setEventTypeFilter(filter.value)}
                      className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                        eventTypeFilter === filter.value
                          ? "bg-blue-600 text-white shadow-lg shadow-blue-500/30"
                          : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-800"
                      }`}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Liste des alertes */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Snapshot
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Type d'événement
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Caméra
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Personne
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Confiance
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Horodatage
                      </th>
                      <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {loading ? (
                      <tr>
                        <td colSpan="7" className="px-6 py-16 text-center">
                          <div className="flex flex-col items-center justify-center text-gray-500 dark:text-gray-400">
                            <svg className="h-10 w-10 animate-spin mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                            </svg>
                            <p className="text-sm">Chargement des alertes…</p>
                          </div>
                        </td>
                      </tr>
                    ) : fetchError ? (
                      <tr>
                        <td colSpan="7" className="px-6 py-16 text-center">
                          <div className="flex flex-col items-center justify-center gap-3">
                            <p className="text-sm text-red-600 dark:text-red-400">{fetchError}</p>
                            <button
                              onClick={loadAlerts}
                              className="px-4 py-2 rounded-xl bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-medium hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors"
                            >
                              Réessayer
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : filteredAlerts.length === 0 ? (
                      <tr>
                        <td colSpan="7" className="px-6 py-16 text-center">
                          <div className="flex flex-col items-center justify-center text-gray-500 dark:text-gray-400">
                            <svg className="h-16 w-16 mb-4 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path d="M12 2v8l4 2" />
                              <circle cx="12" cy="13" r="9" />
                            </svg>
                            <p className="text-base font-medium">Aucune alerte trouvée</p>
                            <p className="text-sm mt-1">Essayez de modifier vos critères de recherche</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredAlerts.map((alert) => (
                        <tr key={alert.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group">
                          <td className="px-6 py-4">
                            <div
                              className={`relative h-16 w-24 rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-800 flex-shrink-0 ${alert.snapshot_url ? "cursor-zoom-in group/snap" : ""}`}
                              onClick={() => alert.snapshot_url && setLightboxAlert(alert)}
                            >
                              {alert.snapshot_url ? (
                                <>
                                  <img
                                    src={
                                      alert.snapshot_url.startsWith("http")
                                        ? alert.snapshot_url
                                        : `/api/images?path=${encodeURIComponent(alert.snapshot_url)}`
                                    }
                                    alt={`Alert ${alert.id}`}
                                    className="w-full h-full object-cover"
                                  />
                                  <div className="absolute inset-0 bg-black/0 group-hover/snap:bg-black/40 transition-colors flex items-center justify-center">
                                    <svg className="h-5 w-5 text-white opacity-0 group-hover/snap:opacity-100 transition-opacity drop-shadow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <circle cx="11" cy="11" r="8" />
                                      <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
                                    </svg>
                                  </div>
                                </>
                              ) : (
                                <div className="w-full h-full flex items-center justify-center">
                                  <svg className="h-8 w-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                    <rect x="3" y="3" width="18" height="18" rx="2" />
                                    <circle cx="8.5" cy="8.5" r="1.5" />
                                    <path d="m21 15-5-5L5 21" />
                                  </svg>
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            {getEventTypeBadge(alert.event_type)}
                          </td>
                          <td className="px-6 py-4">
                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-gray-900 dark:text-white">
                                {alert.camera_nom}
                              </div>
                              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1">
                                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                                  <circle cx="12" cy="10" r="3" />
                                </svg>
                                {alert.camera_location}
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            {alert.person_nom ? (
                              <div className="flex items-center gap-2">
                                <div className="h-8 w-8 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center flex-shrink-0">
                                  <svg className="h-4 w-4 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                                    <circle cx="12" cy="7" r="4" />
                                  </svg>
                                </div>
                                <span className="text-sm text-gray-900 dark:text-white font-medium">
                                  {alert.person_nom}
                                </span>
                              </div>
                            ) : (
                              <span className="text-sm text-gray-500 dark:text-gray-400">—</span>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            {alert.confidence ? (
                              <div className="flex items-center gap-2">
                                <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2 max-w-[80px]">
                                  <div
                                    className={`h-2 rounded-full ${
                                      alert.confidence >= 0.9
                                        ? "bg-green-500"
                                        : alert.confidence >= 0.8
                                        ? "bg-blue-500"
                                        : alert.confidence >= 0.7
                                        ? "bg-yellow-500"
                                        : "bg-red-500"
                                    }`}
                                    style={{ width: `${alert.confidence * 100}%` }}
                                  />
                                </div>
                                <span className={`text-sm font-semibold ${getConfidenceColor(alert.confidence)}`}>
                                  {Math.round(alert.confidence * 100)}%
                                </span>
                              </div>
                            ) : (
                              <span className="text-sm text-gray-500 dark:text-gray-400">—</span>
                            )}
                          </td>
                          <td className="px-6 py-4">
                            <div className="text-sm text-gray-900 dark:text-white font-medium">
                              {formatDateTime(alert.timestamp)}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                              {new Date(alert.timestamp).toLocaleTimeString("fr-FR", {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                              })}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-end gap-2">
                              <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors opacity-0 group-hover:opacity-100">
                                <svg className="h-4 w-4 text-gray-600 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                                  <circle cx="12" cy="12" r="3" />
                                </svg>
                              </button>
                              <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors opacity-0 group-hover:opacity-100">
                                <svg className="h-4 w-4 text-gray-600 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                                </svg>
                              </button>
                              <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors opacity-0 group-hover:opacity-100">
                                <svg className="h-4 w-4 text-gray-600 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      </div>

      {lightboxAlert && (
        <SnapshotLightbox
          alert={lightboxAlert}
          onClose={() => setLightboxAlert(null)}
        />
      )}
    </div>
  );
}

"use client";

// Calcul de l'uptime (corrige ReferenceError)
function getUptime(bootTime) {
  if (!bootTime) return "—";
  const boot = new Date(bootTime.replace(' ', 'T'));
  const now = new Date();
  let diff = Math.floor((now - boot) / 1000);
  const days = Math.floor(diff / (3600 * 24));
  diff -= days * 3600 * 24;
  const hours = Math.floor(diff / 3600);
  diff -= hours * 3600;
  const minutes = Math.floor(diff / 60);
  return `${days}j ${hours}h ${minutes}m`;
}

import { useState, useEffect, useRef } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";

export default function SystemStatusPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [systemData, setSystemData] = useState(null);
  const [prevData, setPrevData] = useState(null); // pour détecter les variations
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showAllDisks, setShowAllDisks] = useState(false);

  const intervalRef = useRef(null);

  const fetchSystemData = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/systemHealth");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setPrevData(systemData); // garde l'ancienne version pour comparaison
      setSystemData(data);
    } catch (err) {
      setError(err.message || "Erreur de connexion à l'API système");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Chargement initial + rafraîchissement auto
  useEffect(() => {
    fetchSystemData();

    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        fetchSystemData(true); // silent = true → pas de spinner à chaque refresh
      }, 30000); // 30 secondes
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh]);

  // Helpers
  const formatBytes = (bytes) => {
    if (typeof bytes !== "number" || bytes <= 0) return "—";
    const units = ["o", "Ko", "Mo", "Go", "To"];
    let size = bytes;
    let i = 0;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  };

  const getTrendIcon = (current = 0, previous = 0) => {
    if (!previous) return null;
    const diff = current - previous;
    if (Math.abs(diff) < 1) return null;
    return diff > 0 ? "↑" : "↓";
  };

  const getColor = (pct = 0) => {
    if (pct < 50) return "#10b981";
    if (pct < 80) return "#f59e0b";
    if (pct < 92) return "#f97316";
    return "#ef4444";
  };

  const getTextColor = (pct = 0) => {
    if (pct < 50) return "text-emerald-600 dark:text-emerald-400";
    if (pct < 80) return "text-amber-600 dark:text-amber-400";
    if (pct < 92) return "text-orange-600 dark:text-orange-400";
    return "text-red-600 dark:text-red-400";
  };

  const CircularGauge = ({ value = 0, label, sublabel, size = 120 }) => {
    const radius = (size - 12) / 2;
    const circ = 2 * Math.PI * radius;
    const offset = circ - (Math.min(value, 100) / 100) * circ;

    return (
      <div className="relative flex flex-col items-center">
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size/2} cy={size/2} r={radius}
            fill="none" stroke="#e5e7eb" strokeWidth="12"
            className="dark:stroke-gray-700"
          />
          <circle
            cx={size/2} cy={size/2} r={radius}
            fill="none"
            stroke={getColor(value)}
            strokeWidth="12"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className={`text-2xl sm:text-3xl font-bold ${getTextColor(value)}`}>
            {value?.toFixed(1) ?? "—"}%
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</div>
        </div>
        {sublabel && (
          <div className="mt-3 text-sm text-gray-600 dark:text-gray-300 text-center">
            {sublabel}
          </div>
        )}
      </div>
    );
  };

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const rootDisk = systemData?.disks?.find(d => d.mountpoint === "/") || {};

  if (user && !["admin"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-gray-50/70 dark:bg-gray-950">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/system-status" />
          <main className={`flex-1 transition-all duration-300 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
            <AccessDenied role={user.role} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50/70 dark:bg-gray-950">
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed(p => !p)}
          currentPath="/Osirion/admin/system-status"
        />

        <main className={`flex-1 transition-all duration-300 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Tableau de bord système"
            subtitle={
              systemData?.general?.hostname
                ? `${systemData.general.hostname} • ${getUptime(systemData.boot_time)}`
                : "—"
            }
            showSearch={false}
            actions={
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={() => setAutoRefresh(!autoRefresh)}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                  <span className="text-gray-600 dark:text-gray-300">Auto (30s)</span>
                </label>

                <button
                  onClick={() => fetchSystemData()}
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60 dark:bg-gray-100 dark:text-gray-900"
                >
                  ↻ {loading ? "..." : "Actualiser"}
                </button>
              </div>
            }
          />

          <div className="p-5 lg:p-8 space-y-8">
            {error && (
              <div className="rounded-xl bg-red-50/80 p-4 text-red-800 border border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-800/50">
                {error}
              </div>
            )}

            {loading && !systemData ? (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400">
                Chargement des métriques système...
              </div>
            ) : systemData && (
              <>
                {/* Vue d'ensemble - jauges */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                    <h3 className="mb-4 text-lg font-semibold">CPU</h3>
                    <CircularGauge
                      value={systemData.cpu?.total_usage_percent ?? 0}
                      label="Utilisation"
                      sublabel={`${systemData.cpu?.physical_cores} cœurs • ${systemData.cpu?.current_frequency_mhz?.toFixed(0) ?? "?"} MHz`}
                    />
                  </div>

                  <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                    <h3 className="mb-4 text-lg font-semibold">Mémoire</h3>
                    <CircularGauge
                      value={systemData.ram?.percent ?? 0}
                      label="Utilisation"
                      sublabel={`${systemData.ram?.used} / ${systemData.ram?.total}`}
                    />
                  </div>

                  <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                    <h3 className="mb-4 text-lg font-semibold">Swap</h3>
                    <CircularGauge
                      value={systemData.swap?.percent ?? 0}
                      label="Utilisation"
                      sublabel={`${systemData.swap?.used} / ${systemData.swap?.total}`}
                    />
                  </div>

                  <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                    <h3 className="mb-4 text-lg font-semibold">Disque racine (/)</h3>
                    <CircularGauge
                      value={rootDisk.percent ?? 0}
                      label="Utilisation"
                      sublabel={rootDisk.used && rootDisk.total ? `${rootDisk.used} / ${rootDisk.total}` : "—"}
                    />
                  </div>
                </div>

                {/* Réseau */}
                <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                  <h2 className="mb-5 text-xl font-bold">Réseau</h2>
                  <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4 mb-4">
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Total envoyé</div>
                      <div className="font-medium">{systemData.network?.total_bytes_sent || "—"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Total reçu</div>
                      <div className="font-medium">{systemData.network?.total_bytes_recv || "—"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Interfaces</div>
                      <div className="font-medium">{systemData.network_interfaces ? Object.keys(systemData.network_interfaces).length : "—"}</div>
                    </div>
                  </div>
                  <div className="mt-4">
                    <h3 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Détail des interfaces</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {systemData.network_interfaces && Object.entries(systemData.network_interfaces).map(([name, iface]) => (
                        <div key={name} className="rounded border p-3 bg-gray-50/70 dark:border-gray-700 dark:bg-gray-800/40">
                          <div className="font-bold text-xs mb-1">{name}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Adresse : {iface.address}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Netmask : {iface.netmask}</div>
                          {iface.broadcast && (
                            <div className="text-xs text-gray-500 dark:text-gray-400">Broadcast : {iface.broadcast}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Infos système rapides */}
                <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                  <h2 className="mb-5 text-xl font-bold">Informations système</h2>
                  <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Hostname</div>
                      <div className="font-medium">{systemData.general?.hostname || "—"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Kernel</div>
                      <div className="font-medium">{systemData.general?.release || "—"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Uptime</div>
                      <div className="font-medium text-green-600 dark:text-green-400">
                        {getUptime(systemData.boot_time)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">Dernier refresh</div>
                      <div className="font-medium">
                        {new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Stockage */}
                <div className="rounded-2xl border bg-white/70 p-6 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/60 shadow-sm">
                  <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-xl font-bold">Stockage</h2>
                    <button
                      onClick={() => setShowAllDisks(!showAllDisks)}
                      className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                    >
                      {showAllDisks ? "Masquer partitions secondaires" : "Voir toutes les partitions"}
                    </button>
                  </div>

                  <div className="space-y-4">
                    {systemData.disks
                      ?.filter(d => !d.mountpoint.startsWith("/snap") && !d.device.startsWith("/dev/loop"))
                      .map((disk, i) => (
                        <div key={i} className="rounded-lg border p-4 dark:border-gray-700">
                          <div className="mb-2 flex items-center justify-between">
                            <div>
                              <div className="font-medium">{disk.mountpoint}</div>
                              <div className="text-sm text-gray-500 dark:text-gray-400">{disk.device}</div>
                            </div>
                            <div className={`text-lg font-bold ${getTextColor(disk.percent)}`}>
                              {disk.percent?.toFixed(1)} % {getTrendIcon(disk.percent, prevData?.disks?.find(p => p.mountpoint === disk.mountpoint)?.percent)}
                            </div>
                          </div>
                          <div className="h-2.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                            <div
                              className="h-full transition-all duration-700 ease-out"
                              style={{ width: `${disk.percent}%`, backgroundColor: getColor(disk.percent) }}
                            />
                          </div>
                          <div className="mt-2 flex justify-between text-sm text-gray-600 dark:text-gray-400">
                            <span>Utilisé : {disk.used}</span>
                            <span>Libre : {disk.free}</span>
                          </div>
                        </div>
                      ))}
                  </div>

                  {showAllDisks && (
                    <div className="mt-6 pt-5 border-t dark:border-gray-700">
                      <h3 className="mb-3 text-sm font-medium text-gray-500 dark:text-gray-400">Partitions secondaires (snap / loop)</h3>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                        {systemData.disks
                          ?.filter(d => d.mountpoint.startsWith("/snap") || d.device.startsWith("/dev/loop"))
                          .map((d, i) => (
                            <div key={i} className="rounded border bg-gray-50/70 p-3 text-sm dark:border-gray-700 dark:bg-gray-800/40">
                              <div className="font-medium truncate">{d.mountpoint}</div>
                              <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{d.device}</div>
                              <div className={`mt-1 font-medium ${getTextColor(d.percent)}`}>
                                {d.percent?.toFixed(1)} %
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
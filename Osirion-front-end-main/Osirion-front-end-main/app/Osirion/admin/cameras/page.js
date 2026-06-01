"use client";

import { useState, useMemo, useEffect } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";

// Liste dynamique des caméras
const BASE_BACKEND_URL = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

export default function CamerasPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("tous");
  const [selectedCameras, setSelectedCameras] = useState([]);
  const [viewMode, setViewMode] = useState("grid"); // "grid" or "table"
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [modalForm, setModalForm] = useState({ cam_name: "", rtsp_url: "", location: "", is_active: true });
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const canWrite = ["admin", "user"].includes(currentRole);

  useEffect(() => {
    const fetchCameras = async () => {
      setLoading(true);
      setError("");
      try {
        

        const response = await fetch("/api/cameras", {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
        });

        if (!response.ok) {
          setError("Erreur lors de la récupération des caméras.");
          setLoading(false);
          return;
        }

        const data = await response.json();
        setCameras(data || []);
      } catch (err) {
        setError("Erreur réseau.");
      } finally {
        setLoading(false);
      }
    };
    fetchCameras();
  }, []);

  // Filtrer les caméras
  const filteredCameras = useMemo(() => {
    return cameras.filter((camera) => {
      const matchesSearch =
        searchQuery === "" ||
        camera.cam_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        String(camera.id).toLowerCase().includes(searchQuery.toLowerCase()) ||
        camera.location?.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesStatus =
        statusFilter === "tous" ||
        (camera.is_active && statusFilter === "active") ||
        (!camera.is_active && statusFilter === "inactive");

      return matchesSearch && matchesStatus;
    });
  }, [cameras, searchQuery, statusFilter]);

  // Compter les caméras par statut
  const statusCounts = useMemo(() => {
    return {
      tous: cameras.length,
      active: cameras.filter((c) => c.is_active).length,
      inactive: cameras.filter((c) => !c.is_active).length,
      maintenance: 0, // Adapter si besoin
    };
  }, [cameras]);

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedCameras(filteredCameras.map((c) => c.id));
    } else {
      setSelectedCameras([]);
    }
  };

  const handleSelectCamera = (cameraId) => {
    setSelectedCameras((prev) =>
      prev.includes(cameraId)
        ? prev.filter((id) => id !== cameraId)
        : [...prev, cameraId]
    );
  };

  const refreshCameras = async () => {
    const r = await fetch("/api/cameras");
    if (r.ok) setCameras(await r.json());
  };

  const handleAddCamera = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setModalError("");
    try {
      const response = await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(modalForm),
      });
      const data = await response.json();
      if (!response.ok) {
        setModalError(data?.message || "Erreur lors de l'ajout.");
        return;
      }
      setShowModal(false);
      setModalForm({ cam_name: "", rtsp_url: "", location: "", is_active: true });
      await refreshCameras();
    } catch {
      setModalError("Erreur réseau.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteCamera = async (cameraId) => {
    if (!window.confirm("Supprimer cette caméra ?")) return;
    try {
      const response = await fetch(`/api/cameras/${cameraId}`, { method: "DELETE" });
      if (response.ok) setCameras((prev) => prev.filter((c) => c.id !== cameraId));
    } catch {}
  };

  const getStatusBadge = (status) => {
    const styles = {
      active:
        "bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400 border-emerald-500/20",
      inactive:
        "bg-gray-500/10 text-gray-600 dark:bg-gray-500/20 dark:text-gray-400 border-gray-500/20",
      maintenance:
        "bg-amber-500/10 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400 border-amber-500/20",
    };

    const labels = {
      active: "En ligne",
      inactive: "Hors ligne",
      maintenance: "Maintenance",
    };

    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${
          styles[status] || styles.inactive
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            status === "active"
              ? "bg-emerald-500 animate-pulse"
              : status === "maintenance"
              ? "bg-amber-500"
              : "bg-gray-400"
          }`}
        />
        {labels[status] || "Hors ligne"}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      {/* Modal ajout caméra */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Ajouter une caméra</h2>
              <button
                onClick={() => setShowModal(false)}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                <svg className="h-5 w-5 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleAddCamera} className="p-6 space-y-4">
              {modalError && (
                <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
                  {modalError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Nom <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={modalForm.cam_name}
                  onChange={(e) => setModalForm((f) => ({ ...f, cam_name: e.target.value }))}
                  placeholder="Caméra Entrée"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  URL RTSP <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={modalForm.rtsp_url}
                  onChange={(e) => setModalForm((f) => ({ ...f, rtsp_url: e.target.value }))}
                  placeholder="rtsp://192.168.1.100:554/stream"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Emplacement
                </label>
                <input
                  type="text"
                  value={modalForm.location}
                  onChange={(e) => setModalForm((f) => ({ ...f, location: e.target.value }))}
                  placeholder="Hall d'entrée, Parking..."
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setModalForm((f) => ({ ...f, is_active: !f.is_active }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    modalForm.is_active ? "bg-blue-600" : "bg-gray-300 dark:bg-gray-600"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      modalForm.is_active ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {modalForm.is_active ? "Active" : "Inactive"}
                </span>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-medium transition-colors shadow-lg shadow-blue-500/30"
                >
                  {submitting ? "Ajout en cours..." : "Ajouter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((prev) => !prev)}
          currentPath="/Osirion/admin/cameras"
        />

        <main
          className={`flex-1 transition-all duration-400 ${
            isCollapsed ? "lg:ml-20" : "lg:ml-80"
          }`}
        >
          {/* Header */}
          <AdminTopBar
            title="Gestion des caméras"
            subtitle={`${cameras.length} caméras • ${statusCounts.active} actives • Dernière sync : il y a 30 sec`}
            searchPlaceholder="Rechercher une caméra..."
            showSearch={false}
            actions={
              <>
                <button className="rounded-xl border border-gray-200 dark:border-gray-800 px-4 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors flex items-center gap-2">
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                  </svg>
                  Exporter
                </button>

                {canWrite && (
                <button
                  onClick={() => { setModalError(""); setShowModal(true); }}
                  className="rounded-xl bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-blue-500/30"
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                  Ajouter une caméra
                </button>
                )}
              </>
            }
          />

          {/* Stats Cards */}
          <div className="px-6 lg:px-10 py-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Caméras */}
              <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 p-5 border border-gray-200/50 dark:border-gray-700/50 hover:shadow-lg hover:scale-[1.02] transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Total Caméras
                    </div>
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">
                      {statusCounts.tous}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-gray-400 to-gray-600 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-white"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <rect x="4" y="7" width="16" height="10" rx="1.5" />
                      <path d="m8 7 2-3h4l2 3" />
                    </svg>
                  </div>
                </div>
                <div className="mt-3 text-xs text-gray-600 dark:text-gray-400">
                  Toutes les caméras du système
                </div>
              </div>

              {/* En ligne */}
              <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 p-5 border border-emerald-200/50 dark:border-emerald-700/50 hover:shadow-lg hover:shadow-emerald-500/20 hover:scale-[1.02] transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-2">
                      En ligne
                    </div>
                    <div className="text-3xl font-bold text-emerald-700 dark:text-emerald-400">
                      {statusCounts.active}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center animate-pulse">
                    <svg
                      className="h-6 w-6 text-white"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M8 12l2 2 4-4" />
                    </svg>
                  </div>
                </div>
                <div className="mt-3 text-xs text-emerald-700 dark:text-emerald-400 font-medium">
                  {statusCounts.tous > 0
                    ? Math.round((statusCounts.active / statusCounts.tous) * 100) + "% du total"
                    : "0%"}
                </div>
              </div>

              {/* Hors ligne */}
              <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 p-5 border border-gray-200/50 dark:border-gray-700/50 hover:shadow-lg hover:scale-[1.02] transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                      Hors ligne
                    </div>
                    <div className="text-3xl font-bold text-gray-700 dark:text-gray-300">
                      {statusCounts.inactive}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-gray-400 to-gray-600 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-white"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M15 9l-6 6M9 9l6 6" />
                    </svg>
                  </div>
                </div>
                <div className="mt-3 text-xs text-gray-600 dark:text-gray-400">
                  Nécessite attention
                </div>
              </div>

              {/* Maintenance */}
              <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-800/20 p-5 border border-amber-200/50 dark:border-amber-700/50 hover:shadow-lg hover:shadow-amber-500/20 hover:scale-[1.02] transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wider mb-2">
                      Maintenance
                    </div>
                    <div className="text-3xl font-bold text-amber-700 dark:text-amber-400">
                      {statusCounts.maintenance}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-white"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                    </svg>
                  </div>
                </div>
                <div className="mt-3 text-xs text-amber-700 dark:text-amber-400 font-medium">
                  En cours de réparation
                </div>
              </div>
            </div>
          </div>

          {/* Filters & Search */}
          <div className="px-6 lg:px-10 py-5 border-t border-gray-200/70 dark:border-gray-800/60">
            <div className="flex flex-col lg:flex-row gap-4">
              {/* Search Bar */}
              <div className="flex-1 relative group">
                <svg
                  className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 group-focus-within:text-blue-500 transition-colors"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  type="text"
                  placeholder="Rechercher par ID, nom ou emplacement..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:text-white transition-all"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    <svg
                      className="h-5 w-5"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>

              {/* View Mode Toggle */}
              <div className="flex items-center gap-2 bg-gray-100 dark:bg-gray-800 rounded-xl p-1">
                <button
                  onClick={() => setViewMode("grid")}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    viewMode === "grid"
                      ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                      : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                  }`}
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="3" y="3" width="7" height="7" />
                    <rect x="14" y="3" width="7" height="7" />
                    <rect x="14" y="14" width="7" height="7" />
                    <rect x="3" y="14" width="7" height="7" />
                  </svg>
                </button>
                <button
                  onClick={() => setViewMode("table")}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    viewMode === "table"
                      ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                      : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                  }`}
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M3 6h18M3 12h18M3 18h18" />
                  </svg>
                </button>
              </div>

              {/* Status Filter */}
              <div className="flex gap-2 overflow-x-auto pb-1">
                {[
                  { value: "tous", label: "Tous", count: statusCounts.tous },
                  { value: "active", label: "En ligne", count: statusCounts.active },
                  { value: "inactive", label: "Hors ligne", count: statusCounts.inactive },
                  { value: "maintenance", label: "Maintenance", count: statusCounts.maintenance },
                ].map((filter) => (
                  <button
                    key={filter.value}
                    onClick={() => setStatusFilter(filter.value)}
                    className={`whitespace-nowrap px-4 py-2.5 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
                      statusFilter === filter.value
                        ? "bg-blue-600 text-white shadow-lg shadow-blue-500/30"
                        : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-800"
                    }`}
                  >
                    {filter.label}
                    <span
                      className={`px-2 py-0.5 rounded-lg text-xs font-semibold ${
                        statusFilter === filter.value
                          ? "bg-white/20 text-white"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                      }`}
                    >
                      {filter.count}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Selected Actions */}
            {selectedCameras.length > 0 && (
              <div className="mt-4 flex items-center gap-3 p-4 rounded-xl bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                <div className="flex items-center gap-2 text-sm font-medium text-blue-900 dark:text-blue-300">
                  <svg
                    className="h-5 w-5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M9 11l3 3L22 4" />
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                  </svg>
                  {selectedCameras.length} caméra(s) sélectionnée(s)
                </div>
                <div className="flex-1" />
                <button className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors">
                  Activer
                </button>
                <button className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium transition-colors">
                  Maintenance
                </button>
                <button className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors">
                  Désactiver
                </button>
              </div>
            )}
          </div>

          {/* Content */}
          <div className="px-6 lg:px-10 py-6">
            {viewMode === "grid" ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
                {filteredCameras.length === 0 ? (
                  <div className="col-span-full flex flex-col items-center justify-center py-20 text-gray-500 dark:text-gray-400">
                    <svg
                      className="h-20 w-20 mb-4 opacity-50"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                    >
                      <rect x="4" y="7" width="16" height="10" rx="1.5" />
                      <path d="m8 7 2-3h4l2 3" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                    <p className="text-lg font-medium">Aucune caméra trouvée</p>
                    <p className="text-sm mt-1">Essayez de modifier vos critères de recherche</p>
                  </div>
                ) : (
                  filteredCameras.map((camera) => (
                    <div
                      key={camera.id}
                      className="group relative overflow-hidden rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 hover:shadow-xl hover:scale-[1.02] transition-all duration-300"
                    >
                      {/* Camera Preview */}
                      <div className="relative h-44 bg-gradient-to-br from-gray-800 to-gray-900 overflow-hidden">
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,_rgba(255,255,255,0.1),transparent_50%)]" />
                        <div className="absolute inset-0 flex items-center justify-center">
                          <svg
                            className="h-16 w-16 text-white/30"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                          >
                            <rect x="4" y="7" width="16" height="10" rx="1.5" />
                            <path d="m8 7 2-3h4l2 3" />
                            <circle cx="12" cy="12" r="3" />
                          </svg>
                        </div>

                        {/* Status Badge */}
                        <div className="absolute top-3 left-3">
                          {getStatusBadge(camera.is_active ? "active" : "inactive")}
                        </div>

                        {/* Checkbox */}
                        <div className="absolute bottom-3 left-3">
                          <input
                            type="checkbox"
                            checked={selectedCameras.includes(camera.id)}
                            onChange={() => handleSelectCamera(camera.id)}
                            className="h-5 w-5 rounded border-2 border-white/50 checked:bg-blue-600 checked:border-blue-600 cursor-pointer"
                          />
                        </div>

                        {/* Quick Actions */}
                        <div className="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button className="p-2 rounded-lg bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm hover:bg-white dark:hover:bg-gray-800 transition-colors">
                            <svg
                              className="h-4 w-4 text-gray-700 dark:text-gray-300"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          </button>
                          {canWrite && (
                          <button
                            onClick={() => handleDeleteCamera(camera.id)}
                            className="p-2 rounded-lg bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors"
                          >
                            <svg
                              className="h-4 w-4 text-red-500"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                              <path d="M10 11v6M14 11v6" />
                              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                            </svg>
                          </button>
                          )}
                        </div>
                      </div>

                      {/* Camera Info */}
                      <div className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1 min-w-0">
                            <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                              {camera.cam_name || "Sans nom"}
                            </h3>
                            <p className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5">
                              {camera.id}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 mb-3">
                          <svg
                            className="h-3.5 w-3.5"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                            <circle cx="12" cy="10" r="3" />
                          </svg>
                          <span className="truncate">{camera.location || "—"}</span>
                        </div>

                        <div className="grid grid-cols-3 gap-2 pt-3 border-t border-gray-200 dark:border-gray-800">
                          <div className="text-center">
                            <div className="text-xs text-gray-500 dark:text-gray-400">RTSP</div>
                            <div className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate">
                              {camera.rtsp_url || "—"}
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Créée</div>
                            <div className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate">
                              {camera.created_at
                                ? new Date(camera.created_at).toLocaleString()
                                : "—"}
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Statut</div>
                            <div className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate">
                              {camera.is_active ? "Active" : "Inactive"}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                      <tr>
                        <th className="w-12 px-6 py-4">
                          <input
                            type="checkbox"
                            checked={
                              filteredCameras.length > 0 &&
                              selectedCameras.length === filteredCameras.length
                            }
                            onChange={handleSelectAll}
                            className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-2 focus:ring-blue-500"
                          />
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                          Caméra
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                          Emplacement
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                          Statut
                        </th>
                        <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {filteredCameras.length === 0 ? (
                        <tr>
                          <td colSpan="5" className="px-6 py-16 text-center">
                            <div className="flex flex-col items-center justify-center text-gray-500 dark:text-gray-400">
                              <svg
                                className="h-16 w-16 mb-4 opacity-50"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                              >
                                <rect x="4" y="7" width="16" height="10" rx="1.5" />
                                <path d="m8 7 2-3h4l2 3" />
                                <circle cx="12" cy="12" r="3" />
                              </svg>
                              <p className="text-base font-medium">Aucune caméra trouvée</p>
                              <p className="text-sm mt-1">
                                Essayez de modifier vos critères de recherche
                              </p>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        filteredCameras.map((camera) => (
                          <tr
                            key={camera.id}
                            className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group"
                          >
                            <td className="px-6 py-4">
                              <input
                                type="checkbox"
                                checked={selectedCameras.includes(camera.id)}
                                onChange={() => handleSelectCamera(camera.id)}
                                className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-2 focus:ring-blue-500"
                              />
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center flex-shrink-0">
                                  <svg
                                    className="h-5 w-5 text-white"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                  >
                                    <rect x="4" y="7" width="16" height="10" rx="1.5" />
                                    <path d="m8 7 2-3h4l2 3" />
                                    <circle cx="12" cy="12" r="3" />
                                  </svg>
                                </div>
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                    {camera.cam_name || "—"}
                                  </div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400 font-mono mt-0.5">
                                    {camera.id}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                                <svg
                                  className="h-4 w-4 flex-shrink-0"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                >
                                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                                  <circle cx="12" cy="10" r="3" />
                                </svg>
                                <span className="truncate">{camera.location || "—"}</span>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              {getStatusBadge(camera.is_active ? "active" : "inactive")}
                            </td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors opacity-0 group-hover:opacity-100">
                                  <svg
                                    className="h-4 w-4 text-gray-600 dark:text-gray-400"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                  >
                                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                                    <circle cx="12" cy="12" r="3" />
                                  </svg>
                                </button>
                                {canWrite && (
                                <button
                                  onClick={() => handleDeleteCamera(camera.id)}
                                  className="p-2 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                                >
                                  <svg
                                    className="h-4 w-4 text-red-500"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                  >
                                    <polyline points="3 6 5 6 21 6" />
                                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                                    <path d="M10 11v6M14 11v6" />
                                    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                                  </svg>
                                </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Pagination */}
            {filteredCameras.length > 0 && (
              <div className="mt-6 flex flex-col sm:flex-row items-center justify-between gap-4 px-2">
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Affichage de{" "}
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {filteredCameras.length}
                  </span>{" "}
                  sur{" "}
                  <span className="font-semibold text-gray-900 dark:text-white">
                    {cameras.length}
                  </span>{" "}
                  caméras
                </div>
                <div className="flex gap-2">
                  <button className="px-4 py-2 border border-gray-200 dark:border-gray-800 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                    Précédent
                  </button>
                  <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium shadow-lg shadow-blue-500/30 transition-all">
                    1
                  </button>
                  <button className="px-4 py-2 border border-gray-200 dark:border-gray-800 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all">
                    Suivant
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
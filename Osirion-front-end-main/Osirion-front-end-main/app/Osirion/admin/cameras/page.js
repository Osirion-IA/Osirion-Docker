"use client";

import { useState, useMemo, useEffect } from "react";
import { useAuth } from "../AuthContext";
import OsShell from "../_osirion/OsShell";
import { PageHeader } from "../_osirion/ui";
import HikSyncButton from "../_osirion/HikSyncButton";

// Liste dynamique des caméras
const BASE_BACKEND_URL = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

// Vue « Plan du site » — plan schématique à pastilles d'état (lat/long normalisées
// dans une boîte 0..1). Fusionnée depuis l'ancienne page « Caméras & site ».
function PlanView({ cameras }) {
  const geo = cameras.filter((c) => c.latitude != null && c.longitude != null);
  const bounds = geo.reduce((b, c) => ({
    minLat: Math.min(b.minLat, c.latitude), maxLat: Math.max(b.maxLat, c.latitude),
    minLng: Math.min(b.minLng, c.longitude), maxLng: Math.max(b.maxLng, c.longitude),
  }), { minLat: Infinity, maxLat: -Infinity, minLng: Infinity, maxLng: -Infinity });
  const pos = (c) => {
    const spanLat = bounds.maxLat - bounds.minLat || 1;
    const spanLng = bounds.maxLng - bounds.minLng || 1;
    return {
      left: `${8 + ((c.longitude - bounds.minLng) / spanLng) * 84}%`,
      top: `${8 + (1 - (c.latitude - bounds.minLat) / spanLat) * 84}%`,
    };
  };
  if (geo.length === 0) {
    return (
      <div className="rounded-os-lg bg-os-card border border-os-border p-8 text-center">
        <p className="text-[13px] text-os-t3">Aucune caméra géolocalisée sur ce périmètre. Renseignez latitude/longitude (en éditant une caméra) pour la placer sur le plan.</p>
      </div>
    );
  }
  return (
    <div className="rounded-os-lg bg-os-card border border-os-border p-5">
      <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Plan du site · {geo.length} caméra(s) géolocalisée(s)</h3>
      <div className="relative w-full max-w-3xl mx-auto aspect-[16/10] rounded-os bg-os-card-2 border border-os-border-2 overflow-hidden">
        <div className="absolute inset-0 opacity-[0.5]" style={{ backgroundImage: "linear-gradient(var(--os-border) 1px, transparent 1px), linear-gradient(90deg, var(--os-border) 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
        {geo.map((c) => (
          <div key={c.id} className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center" style={pos(c)} title={c.cam_name}>
            <span className={`h-3 w-3 rounded-full ring-4 ${c.is_active ? "bg-os-green ring-os-green/20" : "bg-os-t4 ring-os-t4/20"}`} />
            <span className="mt-1 os-num text-[10px] text-os-t3 whitespace-nowrap max-w-[80px] truncate">{c.cam_name || `Caméra ${c.id}`}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CamerasPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("tous");
  const [selectedCameras, setSelectedCameras] = useState([]);
  const [viewMode, setViewMode] = useState("grid"); // "grid" or "table"
  const [cameras, setCameras] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const EMPTY_CAM_FORM = {
    cam_name: "", rtsp_url: "", source_type: "rtsp", location: "", is_active: true,
    latitude: "", longitude: "", bearing: "",
    staffing_enabled: false, staffing_max_agents: "", staffing_min_agents: "",
    staffing_tolerance_s: 300, staffing_work_schedule_id: "",
  };
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = mode ajout
  const [modalForm, setModalForm] = useState(EMPTY_CAM_FORM);
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

  useEffect(() => {
    (async () => {
      const response = await fetch("/api/work-schedules?active_only=true");
      if (response.ok) {
        const data = await response.json();
        setSchedules(Array.isArray(data) ? data : []);
      }
    })();
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

  // Ouvre la modale en mode AJOUT (formulaire vierge).
  const openAddModal = () => {
    setEditingId(null);
    setModalForm(EMPTY_CAM_FORM);
    setModalError("");
    setShowModal(true);
  };

  // Ouvre la modale en mode ÉDITION (préremplie ; géo null → "" pour l'input).
  const openEditModal = (camera) => {
    setEditingId(camera.id);
    setModalForm({
      cam_name: camera.cam_name || "",
      rtsp_url: camera.rtsp_url || "",
      source_type: camera.source_type || "rtsp",
      location: camera.location || "",
      is_active: !!camera.is_active,
      latitude: camera.latitude ?? "",
      longitude: camera.longitude ?? "",
      bearing: camera.bearing ?? "",
      staffing_enabled: camera.staffing_min_agents != null,
      staffing_max_agents: camera.staffing_max_agents ?? "",
      staffing_min_agents: camera.staffing_min_agents ?? "",
      staffing_tolerance_s: camera.staffing_tolerance_s ?? 300,
      staffing_work_schedule_id: camera.staffing_work_schedule_id ?? "",
    });
    setModalError("");
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingId(null);
  };

  // Ajout (POST /api/cameras) ou édition (PUT /api/cameras/{id}). Les champs géo
  // vides sont envoyés à null ; bearing par défaut 0.
  const handleSubmitCamera = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setModalError("");
    const toNum = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
    if (modalForm.staffing_enabled) {
      const maximum = Number(modalForm.staffing_max_agents);
      const minimum = Number(modalForm.staffing_min_agents);
      if (!maximum || !minimum || !modalForm.staffing_work_schedule_id) {
        setModalError("Renseignez l'effectif maximum, le minimum requis et le régime horaire.");
        setSubmitting(false);
        return;
      }
      if (minimum > maximum) {
        setModalError("L'effectif minimum ne peut pas dépasser l'effectif maximum.");
        setSubmitting(false);
        return;
      }
    }
    const payload = {
      cam_name: modalForm.cam_name,
      rtsp_url: modalForm.rtsp_url,
      location: modalForm.location,
      is_active: modalForm.is_active,
      latitude: toNum(modalForm.latitude),
      longitude: toNum(modalForm.longitude),
      bearing: modalForm.bearing === "" ? 0 : Number(modalForm.bearing),
      staffing_max_agents: modalForm.staffing_enabled ? Number(modalForm.staffing_max_agents) : null,
      staffing_min_agents: modalForm.staffing_enabled ? Number(modalForm.staffing_min_agents) : null,
      staffing_tolerance_s: modalForm.staffing_enabled ? Number(modalForm.staffing_tolerance_s) : 300,
      staffing_work_schedule_id: modalForm.staffing_enabled ? Number(modalForm.staffing_work_schedule_id) : null,
    };
    try {
      const url = editingId ? `/api/cameras/${editingId}` : "/api/cameras";
      const method = editingId ? "PUT" : "POST";
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        setModalError(data?.message || "Erreur lors de l'enregistrement.");
        return;
      }
      closeModal();
      setModalForm(EMPTY_CAM_FORM);
      await refreshCameras();
    } catch {
      setModalError("Erreur réseau.");
    } finally {
      setSubmitting(false);
    }
  };

  // (Dés)active une caméra (toggle is_active). Le Core + MediaMTX réagissent au
  // cycle de supervision suivant (arrêt des threads / retrait du chemin).
  const handleToggleActive = async (camera) => {
    const next = !camera.is_active;
    try {
      const response = await fetch(`/api/cameras/${camera.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: next }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        window.alert(data?.message || "Échec de la mise à jour.");
        return;
      }
      setCameras((prev) =>
        prev.map((c) => (c.id === camera.id ? { ...c, is_active: next } : c))
      );
    } catch {
      window.alert("Erreur réseau.");
    }
  };

  // Active/désactive en lot les caméras sélectionnées.
  const handleBulkActive = async (isActive) => {
    const targets = cameras.filter((c) => selectedCameras.includes(c.id));
    await Promise.all(
      targets
        .filter((c) => c.is_active !== isActive)
        .map((c) =>
          fetch(`/api/cameras/${c.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: isActive }),
          })
        )
    );
    setCameras((prev) =>
      prev.map((c) => (selectedCameras.includes(c.id) ? { ...c, is_active: isActive } : c))
    );
    setSelectedCameras([]);
  };

  const handleDeleteCamera = async (cameraId, force = false) => {
    if (!force && !window.confirm("Supprimer définitivement cette caméra ?")) return;
    try {
      const response = await fetch(
        `/api/cameras/${cameraId}${force ? "?force=true" : ""}`,
        { method: "DELETE" }
      );
      if (response.ok) {
        setCameras((prev) => prev.filter((c) => c.id !== cameraId));
        return;
      }
      const data = await response.json().catch(() => ({}));
      // 409 : caméra référencée par des événements → proposer la désactivation
      // (recommandé) ou la suppression en cascade.
      if (response.status === 409) {
        const forceConfirm = window.confirm(
          `${data?.message || "Caméra référencée par des événements."}\n\n` +
          "OK = supprimer quand même (événements + alertes liés perdus).\n" +
          "Annuler = garder (vous pouvez plutôt la désactiver)."
        );
        if (forceConfirm) await handleDeleteCamera(cameraId, true);
        return;
      }
      window.alert(data?.message || "Erreur lors de la suppression.");
    } catch {
      window.alert("Erreur réseau.");
    }
  };

  const getStatusBadge = (status) => {
    const styles = {
      active:
        "bg-os-green text-os-green border-os-border",
      inactive:
        "bg-os-t4 text-os-t3 border-os-border",
      maintenance:
        "bg-os-amber text-os-amber border-os-border",
    };

    const labels = {
      active: "En ligne",
      inactive: "Hors ligne",
      maintenance: "Maintenance",
    };

    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-os text-xs font-medium border ${
          styles[status] || styles.inactive
        }`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            status === "active"
              ? "bg-os-green animate-pulse"
              : status === "maintenance"
              ? "bg-os-amber"
              : "bg-os-t4"
          }`}
        />
        {labels[status] || "Hors ligne"}
      </span>
    );
  };

  return (
    <OsShell>
      {/* Modal ajout caméra */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded-os-lg bg-os-card border border-os-border shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-os-border">
              <h2 className="text-lg font-semibold text-os-t1">
                {editingId ? "Modifier la caméra" : "Ajouter une caméra"}
              </h2>
              <button
                onClick={closeModal}
                className="p-2 rounded-os hover:bg-black/5 transition-colors"
              >
                <svg className="h-5 w-5 text-os-t3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={handleSubmitCamera} className="p-6 space-y-4">
              {modalError && (
                <div className="px-4 py-3 rounded-os border border-os-border text-sm text-os-red">
                  {modalError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-os-t2 mb-1.5">
                  Nom <span className="text-os-red">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={modalForm.cam_name}
                  onChange={(e) => setModalForm((f) => ({ ...f, cam_name: e.target.value }))}
                  placeholder="Caméra Entrée"
                  className="w-full px-4 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-os-t2 mb-1.5">
                  URL RTSP {modalForm.source_type !== "hikcentral" && <span className="text-os-red">*</span>}
                </label>
                <input
                  type="text"
                  required={modalForm.source_type !== "hikcentral"}
                  disabled={modalForm.source_type === "hikcentral"}
                  value={modalForm.rtsp_url}
                  onChange={(e) => setModalForm((f) => ({ ...f, rtsp_url: e.target.value }))}
                  placeholder={modalForm.source_type === "hikcentral" ? "Flux résolu automatiquement par HikCentral" : "rtsp://192.168.1.100:554/stream"}
                  className="w-full px-4 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm font-mono focus:outline-none focus:ring-os-t3 disabled:opacity-60 disabled:cursor-not-allowed"
                />
                {modalForm.source_type === "hikcentral" && (
                  <p className="mt-1.5 text-[11px] text-os-t3">
                    La source vidéo reste gérée par HikCentral ; seuls les paramètres de la caméra sont modifiés ici.
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-os-t2 mb-1.5">
                  Emplacement
                </label>
                <input
                  type="text"
                  value={modalForm.location}
                  onChange={(e) => setModalForm((f) => ({ ...f, location: e.target.value }))}
                  placeholder="Hall d'entrée, Parking..."
                  className="w-full px-4 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3"
                />
              </div>

              {/* Géolocalisation (cartographie). Optionnel : sans lat/lng, la caméra
                  n'apparaît pas sur la carte. bearing = cap 0–360° de l'objectif. */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm font-medium text-os-t2 mb-1.5">Latitude</label>
                  <input
                    type="number"
                    step="any"
                    value={modalForm.latitude}
                    onChange={(e) => setModalForm((f) => ({ ...f, latitude: e.target.value }))}
                    placeholder="14.6928"
                    className="w-full px-3 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-os-t2 mb-1.5">Longitude</label>
                  <input
                    type="number"
                    step="any"
                    value={modalForm.longitude}
                    onChange={(e) => setModalForm((f) => ({ ...f, longitude: e.target.value }))}
                    placeholder="-17.4467"
                    className="w-full px-3 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-os-t2 mb-1.5">Cap (°)</label>
                  <input
                    type="number"
                    min="0"
                    max="360"
                    step="1"
                    value={modalForm.bearing}
                    onChange={(e) => setModalForm((f) => ({ ...f, bearing: e.target.value }))}
                    placeholder="0"
                    className="w-full px-3 py-2.5 bg-os-card-2 border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3"
                  />
                </div>
              </div>

              <div className="rounded-os border border-os-border bg-os-card-2 p-4 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-os-t1">Présence des agents</p>
                    <p className="mt-1 text-[12px] text-os-t3">
                      Compte uniquement les personnes présentes dans les zones « Poste d&apos;agent » de cette caméra.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setModalForm((f) => ({ ...f, staffing_enabled: !f.staffing_enabled }))}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
                      modalForm.staffing_enabled ? "bg-os-cta" : "bg-os-border-2"
                    }`}
                    aria-label="Activer la surveillance de l'effectif"
                  >
                    <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                      modalForm.staffing_enabled ? "translate-x-6" : "translate-x-1"
                    }`} />
                  </button>
                </div>

                {modalForm.staffing_enabled && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="text-[12px] font-medium text-os-t2">
                        Effectif maximum attendu
                        <input type="number" min="1" max="500" required
                          value={modalForm.staffing_max_agents}
                          onChange={(e) => setModalForm((f) => ({ ...f, staffing_max_agents: e.target.value }))}
                          placeholder="ex. 6"
                          className="mt-1.5 w-full px-3 py-2.5 bg-os-card border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3" />
                      </label>
                      <label className="text-[12px] font-medium text-os-t2">
                        Minimum requis
                        <input type="number" min="1" max="500" required
                          value={modalForm.staffing_min_agents}
                          onChange={(e) => setModalForm((f) => ({ ...f, staffing_min_agents: e.target.value }))}
                          placeholder="ex. 4"
                          className="mt-1.5 w-full px-3 py-2.5 bg-os-card border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3" />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="text-[12px] font-medium text-os-t2">
                        Régime horaire
                        <select required value={modalForm.staffing_work_schedule_id}
                          onChange={(e) => setModalForm((f) => ({ ...f, staffing_work_schedule_id: e.target.value }))}
                          className="mt-1.5 w-full px-3 py-2.5 bg-os-card border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3">
                          <option value="">— Choisir —</option>
                          {schedules.map((schedule) => (
                            <option key={schedule.id} value={schedule.id}>{schedule.name}</option>
                          ))}
                        </select>
                      </label>
                      <label className="text-[12px] font-medium text-os-t2">
                        Alerter après
                        <select value={modalForm.staffing_tolerance_s}
                          onChange={(e) => setModalForm((f) => ({ ...f, staffing_tolerance_s: Number(e.target.value) }))}
                          className="mt-1.5 w-full px-3 py-2.5 bg-os-card border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3">
                          {[60, 180, 300, 600, 900].map((seconds) => (
                            <option key={seconds} value={seconds}>{seconds < 60 ? `${seconds} s` : `${seconds / 60} min`}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <p className="text-[11px] text-os-t3">
                      L&apos;alerte est émise si l&apos;effectif reste strictement inférieur au minimum pendant ce délai.
                    </p>
                  </>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setModalForm((f) => ({ ...f, is_active: !f.is_active }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    modalForm.is_active ? "bg-os-cta" : "bg-os-border-2"
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      modalForm.is_active ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
                <span className="text-sm text-os-t2">
                  {modalForm.is_active ? "Active" : "Inactive"}
                </span>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex-1 px-4 py-2.5 rounded-os border border-os-border text-sm font-medium text-os-t2 hover:bg-black/5 transition-colors"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2.5 rounded-os bg-os-cta hover:bg-os-cta-hover disabled:opacity-60 text-white text-sm font-medium transition-colors shadow-lg"
                >
                  {submitting ? "Enregistrement..." : editingId ? "Enregistrer" : "Ajouter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <div className="p-6">
        <PageHeader
          title="Gestion des caméras"
          subtitle={`${cameras.length} caméra(s) · ${statusCounts.active} active(s)`}
          actions={
            <div className="flex items-center gap-2">
              <HikSyncButton onSynced={async () => { const r = await fetch("/api/cameras"); if (r.ok) setCameras(await r.json()); }} />
              {canWrite ? (
                <button
                  onClick={openAddModal}
                  className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover inline-flex items-center gap-2"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                  Ajouter une caméra
                </button>
              ) : null}
            </div>
          }
        />

          {/* Stats Cards */}
          <div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Total Caméras */}
              <div className="group relative overflow-hidden rounded-os-lg bg-os-card p-5 border border-os-border transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-os-t3 mb-2">
                      Total Caméras
                    </div>
                    <div className="os-num text-[26px] leading-none font-bold text-os-t1">
                      {statusCounts.tous}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-os bg-os-card-2 border border-os-border-2 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-os-t3"
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
                <div className="mt-3 text-xs text-os-t3">
                  Toutes les caméras du système
                </div>
              </div>

              {/* En ligne */}
              <div className="group relative overflow-hidden rounded-os-lg bg-os-card p-5 border border-os-border transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-os-green mb-2">
                      En ligne
                    </div>
                    <div className="os-num text-[26px] leading-none font-bold text-os-green">
                      {statusCounts.active}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-os bg-os-card-2 border border-os-border-2 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-os-t3"
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
                <div className="mt-3 text-xs text-os-green font-medium">
                  {statusCounts.tous > 0
                    ? Math.round((statusCounts.active / statusCounts.tous) * 100) + "% du total"
                    : "0%"}
                </div>
              </div>

              {/* Hors ligne */}
              <div className="group relative overflow-hidden rounded-os-lg bg-os-card p-5 border border-os-border transition-all duration-300">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-os-t3 mb-2">
                      Hors ligne
                    </div>
                    <div className="os-num text-[26px] leading-none font-bold text-os-t2">
                      {statusCounts.inactive}
                    </div>
                  </div>
                  <div className="h-12 w-12 rounded-os bg-os-card-2 border border-os-border-2 flex items-center justify-center">
                    <svg
                      className="h-6 w-6 text-os-t3"
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
                <div className="mt-3 text-xs text-os-t3">
                  Nécessite attention
                </div>
              </div>

            </div>
          </div>

          {/* Filters & Search */}
          <div className="mt-5">
            <div className="flex flex-col lg:flex-row gap-4">
              {/* Search Bar */}
              <div className="flex-1 relative group">
                <svg
                  className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-os-t4 group-focus-within:text-os-t2 transition-colors"
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
                  className="w-full pl-12 pr-4 py-3 bg-os-card border border-os-border rounded-os text-sm focus:outline-none focus:ring-os-t3 transition-all"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-os-t4 hover:text-os-t3"
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
              <div className="flex items-center gap-2 bg-os-card-2 rounded-os p-1">
                <button
                  onClick={() => setViewMode("grid")}
                  className={`px-4 py-2 rounded-os text-sm font-medium transition-all ${
                    viewMode === "grid"
                      ? "bg-os-card text-os-t1 shadow-sm"
                      : "text-os-t3 hover:text-os-t1"
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
                  className={`px-4 py-2 rounded-os text-sm font-medium transition-all ${
                    viewMode === "table"
                      ? "bg-os-card text-os-t1 shadow-sm"
                      : "text-os-t3 hover:text-os-t1"
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
                <button
                  onClick={() => setViewMode("plan")}
                  title="Plan du site"
                  className={`px-4 py-2 rounded-os text-sm font-medium transition-all ${
                    viewMode === "plan" ? "bg-os-card text-os-t1 shadow-sm" : "text-os-t3 hover:text-os-t1"
                  }`}
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 20l-5.5 1.8a1 1 0 0 1-1.3-1V5.7a1 1 0 0 1 .7-1L9 3m0 17 6-2m-6 2V3m6 15 5.5 1.8a1 1 0 0 0 1.3-1V5.7a1 1 0 0 0-.7-1L15 3m0 15V3M15 3 9 5" />
                  </svg>
                </button>
              </div>

              {/* Status Filter */}
              <div className="flex gap-2 overflow-x-auto pb-1">
                {[
                  { value: "tous", label: "Tous", count: statusCounts.tous },
                  { value: "active", label: "En ligne", count: statusCounts.active },
                  { value: "inactive", label: "Hors ligne", count: statusCounts.inactive },
                ].map((filter) => (
                  <button
                    key={filter.value}
                    onClick={() => setStatusFilter(filter.value)}
                    className={`whitespace-nowrap px-4 py-2.5 rounded-os text-sm font-medium transition-all flex items-center gap-2 ${
                      statusFilter === filter.value
                        ? "bg-os-primary text-os-on-primary shadow-lg"
                        : "bg-os-card text-os-t2 hover:bg-black/5 border border-os-border"
                    }`}
                  >
                    {filter.label}
                    <span
                      className={`px-2 py-0.5 rounded-os text-xs font-semibold ${
                        statusFilter === filter.value
                          ? "bg-os-card text-white"
                          : "bg-os-card-2 text-os-t3"
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
              <div className="mt-4 flex items-center gap-3 p-4 rounded-os bg-os-card-2 border border-os-border">
                <div className="flex items-center gap-2 text-sm font-medium text-os-t1">
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
                {canWrite && (
                  <>
                    <button
                      onClick={() => handleBulkActive(true)}
                      className="px-4 py-2 rounded-os bg-os-cta hover:bg-os-cta-hover text-white text-sm font-medium transition-colors"
                    >
                      Activer
                    </button>
                    <button
                      onClick={() => handleBulkActive(false)}
                      className="px-4 py-2 rounded-os bg-os-cta hover:bg-os-cta-hover text-white text-sm font-medium transition-colors"
                    >
                      Désactiver
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Content */}
          <div className="mt-4">
            {viewMode === "plan" ? (
              <PlanView cameras={filteredCameras} />
            ) : viewMode === "grid" ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
                {filteredCameras.length === 0 ? (
                  <div className="col-span-full flex flex-col items-center justify-center py-20 text-os-t3">
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
                      className="group relative overflow-hidden rounded-os-lg bg-os-card border border-os-border transition-all duration-300"
                    >
                      {/* Camera Preview */}
                      <div className="relative h-44 bg-[#0d0f12] overflow-hidden">
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
                            className="h-5 w-5 rounded border-2 border-white/50 checked:bg-os-cta checked:border-os-cta cursor-pointer"
                          />
                        </div>

                        {/* Quick Actions */}
                        <div className="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button className="p-2 rounded-os bg-os-card backdrop-blur-sm hover:bg-os-card transition-colors">
                            <svg
                              className="h-4 w-4 text-os-t2"
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
                            onClick={() => handleToggleActive(camera)}
                            title={camera.is_active ? "Désactiver" : "Activer"}
                            className="p-2 rounded-os bg-os-card backdrop-blur-sm hover:bg-os-card transition-colors"
                          >
                            <svg
                              className={`h-4 w-4 ${camera.is_active ? "text-os-green" : "text-os-t4"}`}
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                            >
                              <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
                              <line x1="12" y1="2" x2="12" y2="12" />
                            </svg>
                          </button>
                          )}
                          {canWrite && (
                          <button
                            onClick={() => openEditModal(camera)}
                            title="Modifier"
                            className="p-2 rounded-os bg-os-card backdrop-blur-sm hover:bg-os-card transition-colors"
                          >
                            <svg className="h-4 w-4 text-os-t2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M12 20h9" />
                              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
                            </svg>
                          </button>
                          )}
                          {canWrite && (
                          <button
                            onClick={() => handleDeleteCamera(camera.id)}
                            className="p-2 rounded-os bg-os-card backdrop-blur-sm hover:opacity-90 transition-colors"
                          >
                            <svg
                              className="h-4 w-4 text-os-red"
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
                            <h3 className="font-semibold text-os-t1 truncate">
                              {camera.cam_name || "Sans nom"}
                            </h3>
                            <p className="text-xs text-os-t3 font-mono mt-0.5">
                              {camera.id}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 text-xs text-os-t3 mb-3">
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

                        {camera.staffing_min_agents != null && (
                          <div className="mb-3 rounded-os border border-os-border bg-os-card-2 px-3 py-2">
                            <p className="text-[11px] font-semibold text-os-t2">
                              Effectif : minimum {camera.staffing_min_agents} · maximum {camera.staffing_max_agents}
                            </p>
                            <p className="mt-0.5 text-[10px] text-os-t3 truncate">
                              {camera.staffing_schedule?.name || "⚠ régime désactivé ou supprimé"}
                            </p>
                          </div>
                        )}

                        <div className="grid grid-cols-3 gap-2 pt-3 border-t border-os-border">
                          <div className="text-center">
                            <div className="text-xs text-os-t3">RTSP</div>
                            <div className="text-xs font-mono text-os-t2 truncate">
                              {camera.rtsp_url || "—"}
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-os-t3">Créée</div>
                            <div className="text-xs font-mono text-os-t2 truncate">
                              {camera.created_at
                                ? new Date(camera.created_at).toLocaleString()
                                : "—"}
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-os-t3">Statut</div>
                            <div className="text-xs font-mono text-os-t2 truncate">
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
              <div className="bg-os-card rounded-os-lg border border-os-border overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-os-card-2 border-b border-os-border">
                      <tr>
                        <th className="w-12 px-6 py-4">
                          <input
                            type="checkbox"
                            checked={
                              filteredCameras.length > 0 &&
                              selectedCameras.length === filteredCameras.length
                            }
                            onChange={handleSelectAll}
                            className="rounded border-os-border text-os-blue focus:ring-os-t3"
                          />
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3">
                          Caméra
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3">
                          Emplacement
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3">
                          Statut
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3">
                          Effectif agents
                        </th>
                        <th className="px-6 py-4 text-right text-xs font-semibold text-os-t3">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-os-border">
                      {filteredCameras.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="px-6 py-16 text-center">
                            <div className="flex flex-col items-center justify-center text-os-t3">
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
                            className="hover:bg-black/5 transition-colors group"
                          >
                            <td className="px-6 py-4">
                              <input
                                type="checkbox"
                                checked={selectedCameras.includes(camera.id)}
                                onChange={() => handleSelectCamera(camera.id)}
                                className="rounded border-os-border text-os-blue focus:ring-os-t3"
                              />
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <div className="h-12 w-12 rounded-os bg-[#0d0f12] flex items-center justify-center flex-shrink-0">
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
                                  <div className="text-sm font-semibold text-os-t1 truncate">
                                    {camera.cam_name || "—"}
                                  </div>
                                  <div className="text-xs text-os-t3 font-mono mt-0.5">
                                    {camera.id}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-2 text-sm text-os-t3">
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
                            <td className="px-6 py-4">
                              {camera.staffing_min_agents != null ? (
                                <div className="text-[12px] text-os-t2">
                                  <span className="os-num font-semibold">min {camera.staffing_min_agents} / max {camera.staffing_max_agents}</span>
                                  <span className="block text-[11px] text-os-t4 truncate max-w-40">
                                    {camera.staffing_schedule?.name || "Régime indisponible"}
                                  </span>
                                </div>
                              ) : <span className="text-[12px] text-os-t4">Non configuré</span>}
                            </td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button className="p-2 hover:bg-black/5 rounded-os transition-colors opacity-0 group-hover:opacity-100">
                                  <svg
                                    className="h-4 w-4 text-os-t3"
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
                                  onClick={() => handleToggleActive(camera)}
                                  title={camera.is_active ? "Désactiver" : "Activer"}
                                  className="p-2 hover:bg-black/5 rounded-os transition-colors opacity-0 group-hover:opacity-100"
                                >
                                  <svg
                                    className={`h-4 w-4 ${camera.is_active ? "text-os-green" : "text-os-t4"}`}
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                  >
                                    <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
                                    <line x1="12" y1="2" x2="12" y2="12" />
                                  </svg>
                                </button>
                                )}
                                {canWrite && (
                                <button
                                  onClick={() => openEditModal(camera)}
                                  title="Modifier"
                                  className="p-2 hover:bg-black/5 rounded-os transition-colors opacity-0 group-hover:opacity-100"
                                >
                                  <svg className="h-4 w-4 text-os-t3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M12 20h9" />
                                    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
                                  </svg>
                                </button>
                                )}
                                {canWrite && (
                                <button
                                  onClick={() => handleDeleteCamera(camera.id)}
                                  className="p-2 hover:opacity-90 rounded-os transition-colors opacity-0 group-hover:opacity-100"
                                >
                                  <svg
                                    className="h-4 w-4 text-os-red"
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
                <div className="text-sm text-os-t3">
                  Affichage de{" "}
                  <span className="font-semibold text-os-t1">
                    {filteredCameras.length}
                  </span>{" "}
                  sur{" "}
                  <span className="font-semibold text-os-t1">
                    {cameras.length}
                  </span>{" "}
                  caméras
                </div>
                <div className="flex gap-2">
                  <button className="px-4 py-2 border border-os-border rounded-os text-sm font-medium text-os-t2 hover:bg-black/5 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                    Précédent
                  </button>
                  <button className="px-4 py-2 bg-os-cta hover:bg-os-cta-hover text-white rounded-os text-sm font-medium shadow-lg transition-all">
                    1
                  </button>
                  <button className="px-4 py-2 border border-os-border rounded-os text-sm font-medium text-os-t2 hover:bg-black/5 transition-all">
                    Suivant
                  </button>
                </div>
              </div>
            )}
          </div>
      </div>
    </OsShell>
  );
}

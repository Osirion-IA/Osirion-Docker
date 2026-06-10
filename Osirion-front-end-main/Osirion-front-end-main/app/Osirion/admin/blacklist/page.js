"use client";

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied, useCanDo } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

// ─── Formulaire d'ajout ───────────────────────────────────────────────────────

const EMPTY_FORM = {
  first_name: "",
  last_name: "",
  phone: "",
  email: "",
  addresse: "",
  image_url: null,
};

function AddPersonModal({ onClose, onSuccess }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [preview, setPreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef();

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setForm((prev) => ({ ...prev, image_url: file }));
    setPreview(URL.createObjectURL(file));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!form.image_url) {
      setError("Veuillez sélectionner une photo.");
      return;
    }

    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("first_name", form.first_name.trim());
      fd.append("last_name", form.last_name.trim());
      fd.append("phone", form.phone.trim());
      fd.append("email", form.email.trim());
      fd.append("addresse", form.addresse.trim());
      fd.append("image_url", form.image_url);

      const res = await fetchWithRefresh("/api/people", { method: "POST", body: fd });
      if (!res) return;

      const data = await res.json();
      if (!res.ok) {
        setError(data?.message || "Erreur lors de l'ajout.");
      } else {
        onSuccess(data?.message || "Personne ajoutée avec succès.");
      }
    } catch {
      setError("Erreur réseau.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              Ajouter à la blacklist
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Une photo nette et frontale est requise pour la reconnaissance faciale
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-500"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Photo Upload */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-2">
              Photo <span className="text-red-500">*</span>
            </label>
            <div
              onClick={() => fileRef.current?.click()}
              className="relative flex flex-col items-center justify-center h-36 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 cursor-pointer hover:border-blue-400 dark:hover:border-blue-500 transition-colors overflow-hidden"
            >
              {preview ? (
                <img src={preview} alt="Aperçu" className="w-full h-full object-cover" />
              ) : (
                <div className="flex flex-col items-center gap-2 text-gray-400 dark:text-gray-500">
                  <svg className="h-10 w-10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <path d="m21 15-5-5L5 21" />
                  </svg>
                  <span className="text-sm font-medium">Cliquer pour choisir une photo</span>
                  <span className="text-xs">JPG, PNG — photo frontale recommandée</span>
                </div>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={handleFile}
            />
            {preview && (
              <button
                type="button"
                onClick={() => { setPreview(null); setForm((p) => ({ ...p, image_url: null })); fileRef.current.value = ""; }}
                className="mt-1.5 text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400"
              >
                Supprimer la photo
              </button>
            )}
          </div>

          {/* Nom / Prénom */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
                Prénom <span className="text-red-500">*</span>
              </label>
              <input
                name="first_name"
                value={form.first_name}
                onChange={handleChange}
                required
                placeholder="Prénom"
                className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
                Nom <span className="text-red-500">*</span>
              </label>
              <input
                name="last_name"
                value={form.last_name}
                onChange={handleChange}
                required
                placeholder="Nom de famille"
                className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Téléphone */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
              Téléphone <span className="text-red-500">*</span>
            </label>
            <input
              name="phone"
              value={form.phone}
              onChange={handleChange}
              required
              placeholder="+33 6 00 00 00 00"
              className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Email */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              required
              placeholder="exemple@email.com"
              className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Adresse */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-1.5">
              Adresse <span className="text-red-500">*</span>
            </label>
            <input
              name="addresse"
              value={form.addresse}
              onChange={handleChange}
              required
              placeholder="12 rue de la Paix, 75001 Paris"
              className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2.5 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
              <svg className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
              </svg>
              <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* Submit */}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 px-4 py-2.5 rounded-xl bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 text-white dark:text-gray-900 text-sm font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                  </svg>
                  Analyse en cours...
                </>
              ) : (
                "Ajouter à la blacklist"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Lightbox ────────────────────────────────────────────────────────────────

function ImageLightbox({ person, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const src = `/api/images?path=${encodeURIComponent(person.image_url)}`;
  const name = `${person.first_name} ${person.last_name}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Contenu */}
      <div className="relative flex flex-col items-center max-w-3xl w-full max-h-[90vh]">
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
          alt={name}
          className="max-h-[75vh] max-w-full rounded-2xl object-contain shadow-2xl"
        />

        {/* Nom sous l'image */}
        <div className="mt-4 px-4 py-2 rounded-xl bg-white/10 backdrop-blur-sm border border-white/20">
          <p className="text-white text-sm font-semibold text-center">{name}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Page principale ──────────────────────────────────────────────────────────

export default function BlacklistPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState("grid");
  const [showModal, setShowModal] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [lightboxPerson, setLightboxPerson] = useState(null);

  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const canManageBlacklist = useCanDo("manage-blacklist");

  const loadPeople = useCallback(async () => {
    setLoading(true);
    setFetchError("");
    try {
      const res = await fetchWithRefresh("/api/people");
      if (!res) return;
      if (!res.ok) {
        const d = await res.json();
        setFetchError(d?.message || "Erreur de chargement.");
        return;
      }
      const data = await res.json();
      setPeople(Array.isArray(data) ? data : []);
    } catch {
      setFetchError("Impossible de contacter le serveur.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  const handleAddSuccess = (msg) => {
    setShowModal(false);
    setSuccessMsg(msg);
    loadPeople();
    setTimeout(() => setSuccessMsg(""), 4000);
  };

  // (Dé)marque une personne « sous surveillance ». Mise à jour optimiste avec
  // rollback si l'appel échoue. Le Core lit ce statut → alerte (toast/son).
  const toggleBlacklist = async (person) => {
    const next = !person.is_blacklisted;
    setPeople((prev) => prev.map((p) => (p.id === person.id ? { ...p, is_blacklisted: next } : p)));
    try {
      const res = await fetchWithRefresh(`/api/people/${person.id}/blacklist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blacklisted: next }),
      });
      if (!res || !res.ok) throw new Error("toggle failed");
    } catch {
      // Rollback visuel en cas d'échec réseau/serveur.
      setPeople((prev) => prev.map((p) => (p.id === person.id ? { ...p, is_blacklisted: !next } : p)));
    }
  };

  const filteredPeople = useMemo(() => {
    if (!searchQuery) return people;
    const q = searchQuery.toLowerCase();
    return people.filter((p) => {
      const fullName = `${p.first_name} ${p.last_name}`.toLowerCase();
      return (
        fullName.includes(q) ||
        (p.email || "").toLowerCase().includes(q) ||
        (p.phone || "").toLowerCase().includes(q) ||
        (p.addresse || "").toLowerCase().includes(q)
      );
    });
  }, [people, searchQuery]);

  const formatDate = (dateString) => {
    if (!dateString) return "—";
    return new Date(dateString).toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  const getInitials = (first, last) =>
    `${(first || "?")[0]}${(last || "?")[0]}`.toUpperCase();

  if (user && !["admin", "user"].includes(user.role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/blacklist" />
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
          currentPath="/Osirion/admin/blacklist"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Blacklist"
            subtitle={
              loading
                ? "Chargement..."
                : `${people.length} personne${people.length > 1 ? "s" : ""} enregistrée${people.length > 1 ? "s" : ""}`
            }
            showSearch={false}
            actions={
              canManageBlacklist ? (
                <button
                  onClick={() => setShowModal(true)}
                  className="rounded-xl bg-gray-900 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-100 text-white dark:text-gray-900 px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                  Ajouter à la blacklist
                </button>
              ) : null
            }
          />

          {/* Toast succès */}
          {successMsg && (
            <div className="mx-6 lg:mx-10 mt-4 flex items-center gap-3 p-4 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
              <svg className="h-5 w-5 text-green-500 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 6L9 17l-5-5" />
              </svg>
              <p className="text-sm font-medium text-green-700 dark:text-green-400">{successMsg}</p>
            </div>
          )}

          {/* Stats */}
          <div className="px-6 lg:px-10 py-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="rounded-2xl bg-white dark:bg-gray-900 p-5 border border-gray-200 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                  Total Blacklist
                </div>
                <div className="text-3xl font-bold text-gray-900 dark:text-white">
                  {loading ? "—" : people.length}
                </div>
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">Personnes surveillées</div>
              </div>

              <div className="rounded-2xl bg-white dark:bg-gray-900 p-5 border border-gray-200 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                  Ce mois
                </div>
                <div className="text-3xl font-bold text-gray-900 dark:text-white">
                  {loading ? "—" : people.filter((p) => {
                    if (!p.created_at) return false;
                    const d = new Date(p.created_at);
                    const now = new Date();
                    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
                  }).length}
                </div>
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">Ajouts ce mois-ci</div>
              </div>

              <div className="rounded-2xl bg-white dark:bg-gray-900 p-5 border border-gray-200 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
                  Résultats filtrés
                </div>
                <div className="text-3xl font-bold text-gray-900 dark:text-white">
                  {loading ? "—" : filteredPeople.length}
                </div>
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  {searchQuery ? `Recherche "${searchQuery}"` : "Tous affichés"}
                </div>
              </div>
            </div>
          </div>

          {/* Barre de recherche + toggle vue */}
          <div className="px-6 lg:px-10 pb-5 border-t border-gray-200/70 dark:border-gray-800/60 pt-5">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex-1 relative group">
                <svg className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 group-focus-within:text-blue-500 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  type="text"
                  placeholder="Rechercher par nom, email, téléphone..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:text-white"
                />
                {searchQuery && (
                  <button onClick={() => setSearchQuery("")} className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
                  </button>
                )}
              </div>

              <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1">
                {["grid", "table"].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setViewMode(mode)}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      viewMode === mode
                        ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                        : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                    }`}
                  >
                    {mode === "grid" ? (
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
                        <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
                      </svg>
                    ) : (
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M3 6h18M3 12h18M3 18h18" />
                      </svg>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Contenu */}
          <div className="px-6 lg:px-10 pb-10">
            {/* État chargement */}
            {loading && (
              <div className="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-500">
                <svg className="h-10 w-10 animate-spin mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
                <p className="text-sm">Chargement de la blacklist...</p>
              </div>
            )}

            {/* Erreur fetch */}
            {!loading && fetchError && (
              <div className="flex flex-col items-center justify-center py-24">
                <div className="flex items-center gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 max-w-md">
                  <svg className="h-5 w-5 text-red-500 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
                  </svg>
                  <p className="text-sm text-red-700 dark:text-red-400">{fetchError}</p>
                </div>
                <button
                  onClick={loadPeople}
                  className="mt-4 px-4 py-2 rounded-xl bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-medium hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors"
                >
                  Réessayer
                </button>
              </div>
            )}

            {/* Liste vide */}
            {!loading && !fetchError && people.length === 0 && (
              <div className="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-500">
                <svg className="h-20 w-20 mb-4 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" /><path d="m4.93 4.93 14.14 14.14" />
                </svg>
                <p className="text-lg font-medium">Blacklist vide</p>
                <p className="text-sm mt-1">Aucune personne enregistrée pour l'instant</p>
                <button
                  onClick={() => setShowModal(true)}
                  className="mt-6 px-5 py-2.5 rounded-xl bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-semibold hover:bg-gray-800 dark:hover:bg-gray-100 transition-colors flex items-center gap-2"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                  Ajouter la première personne
                </button>
              </div>
            )}

            {/* Filtre sans résultats */}
            {!loading && !fetchError && people.length > 0 && filteredPeople.length === 0 && (
              <div className="flex flex-col items-center justify-center py-24 text-gray-400 dark:text-gray-500">
                <svg className="h-16 w-16 mb-4 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                </svg>
                <p className="font-medium">Aucun résultat pour "{searchQuery}"</p>
                <button onClick={() => setSearchQuery("")} className="mt-3 text-sm text-blue-500 hover:text-blue-700 dark:hover:text-blue-400">
                  Effacer la recherche
                </button>
              </div>
            )}

            {/* Vue Grille */}
            {!loading && !fetchError && filteredPeople.length > 0 && viewMode === "grid" && (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
                {filteredPeople.map((person, idx) => (
                  <div
                    key={person.email || idx}
                    className="group relative overflow-hidden rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 hover:shadow-xl hover:scale-[1.02] transition-all duration-300"
                  >
                    {/* Photo */}
                    <div
                      className={`relative h-36 bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-700 flex items-center justify-center border-b border-gray-200 dark:border-gray-700 overflow-hidden ${person.image_url ? "cursor-zoom-in" : ""}`}
                      onClick={() => person.image_url && setLightboxPerson(person)}
                    >
                      {person.image_url ? (
                        <>
                          <img
                            src={`/api/images?path=${encodeURIComponent(person.image_url)}`}
                            alt={`${person.first_name} ${person.last_name}`}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                              e.currentTarget.nextSibling.style.display = "flex";
                            }}
                          />
                          {/* Overlay zoom au survol */}
                          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                            <svg className="h-8 w-8 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-lg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="11" cy="11" r="8" />
                              <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
                            </svg>
                          </div>
                        </>
                      ) : null}
                      <div
                        className={`h-20 w-20 rounded-full bg-gray-900 dark:bg-white flex items-center justify-center ${person.image_url ? "hidden" : ""}`}
                        style={{ display: person.image_url ? "none" : "flex" }}
                      >
                        <span className="text-2xl font-bold text-white dark:text-gray-900">
                          {getInitials(person.first_name, person.last_name)}
                        </span>
                      </div>

                      {person.is_blacklisted && (
                        <span className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-rose-600 text-white text-[10px] font-bold shadow flex items-center gap-1">
                          ⚠ Surveillé
                        </span>
                      )}
                    </div>

                    {/* Infos */}
                    <div className="p-4">
                      <h3 className="font-semibold text-gray-900 dark:text-white text-lg leading-tight">
                        {person.first_name} {person.last_name}
                      </h3>

                      <div className="mt-3 space-y-1.5">
                        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.6 2.22h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 9.35a16 16 0 0 0 6.29 6.29l.9-.9a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
                          </svg>
                          <span className="truncate">{person.phone}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                            <polyline points="22,6 12,13 2,6" />
                          </svg>
                          <span className="truncate">{person.email}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                            <circle cx="12" cy="10" r="3" />
                          </svg>
                          <span className="truncate">{person.addresse}</span>
                        </div>
                      </div>

                      <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-2">
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                          Ajouté le {formatDate(person.created_at)}
                        </span>
                        {canManageBlacklist && (
                          <button
                            onClick={() => toggleBlacklist(person)}
                            className={`text-[11px] font-semibold px-2.5 py-1 rounded-lg transition-colors ${
                              person.is_blacklisted
                                ? "bg-rose-100 text-rose-700 hover:bg-rose-200 dark:bg-rose-900/30 dark:text-rose-300"
                                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
                            }`}
                          >
                            {person.is_blacklisted ? "Retirer surveillance" : "Mettre sous surveillance"}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Vue Tableau */}
            {!loading && !fetchError && filteredPeople.length > 0 && viewMode === "table" && (
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                      <tr>
                        {["Personne", "Téléphone", "Email", "Adresse", "Date d'ajout"].map((h) => (
                          <th key={h} className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                      {filteredPeople.map((person, idx) => (
                        <tr key={person.email || idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div
                                className={`relative h-10 w-10 rounded-xl overflow-hidden bg-gray-900 dark:bg-white flex items-center justify-center flex-shrink-0 ${person.image_url ? "cursor-zoom-in group/thumb" : ""}`}
                                onClick={() => person.image_url && setLightboxPerson(person)}
                              >
                                {person.image_url ? (
                                  <>
                                    <img
                                      src={`/api/images?path=${encodeURIComponent(person.image_url)}`}
                                      alt={`${person.first_name} ${person.last_name}`}
                                      className="w-full h-full object-cover"
                                      onError={(e) => {
                                        e.currentTarget.style.display = "none";
                                        e.currentTarget.nextSibling.style.display = "flex";
                                      }}
                                    />
                                    <div className="absolute inset-0 bg-black/0 group-hover/thumb:bg-black/40 transition-colors flex items-center justify-center">
                                      <svg className="h-4 w-4 text-white opacity-0 group-hover/thumb:opacity-100 transition-opacity" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                        <circle cx="11" cy="11" r="8" />
                                        <path d="m21 21-4.35-4.35M11 8v6M8 11h6" />
                                      </svg>
                                    </div>
                                  </>
                                ) : null}
                                <span
                                  className="text-sm font-bold text-white dark:text-gray-900 w-full h-full items-center justify-center"
                                  style={{ display: person.image_url ? "none" : "flex" }}
                                >
                                  {getInitials(person.first_name, person.last_name)}
                                </span>
                              </div>
                              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                                {person.first_name} {person.last_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">{person.phone}</td>
                          <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">{person.email}</td>
                          <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400 max-w-[200px] truncate">{person.addresse}</td>
                          <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">{formatDate(person.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Modal ajout */}
      {showModal && (
        <AddPersonModal
          onClose={() => setShowModal(false)}
          onSuccess={handleAddSuccess}
        />
      )}

      {/* Lightbox image */}
      {lightboxPerson && (
        <ImageLightbox
          person={lightboxPerson}
          onClose={() => setLightboxPerson(null)}
        />
      )}
    </div>
  );
}

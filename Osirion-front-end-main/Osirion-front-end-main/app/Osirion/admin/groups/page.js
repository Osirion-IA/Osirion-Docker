"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";

// Page « Groupes de caméras » (VMS) : CRUD, bascule de module en masse
// (facial / LPR) et gestion des membres. Consomme les proxys /api/groups/* et
// /api/cameras. La bascule d'un module est appliquée à chaud par le Core.

const EMPTY_FORM = { name: "", description: "", is_facial_active: true, is_lpr_active: true };

export default function GroupsPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [groups, setGroups] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null); // groupe en cours de mutation

  // Modal création / édition
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");

  // Modal gestion des membres (caméras d'un groupe)
  const [membersGroup, setMembersGroup] = useState(null);

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const canWrite = ["admin", "user"].includes(currentRole);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [gr, cr] = await Promise.all([
        fetch("/api/groups"),
        fetch("/api/cameras"),
      ]);
      if (!gr.ok) throw new Error("groups");
      setGroups((await gr.json()) || []);
      setCameras(cr.ok ? (await cr.json()) || [] : []);
    } catch {
      setError("Erreur lors du chargement des groupes.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const camerasById = useMemo(() => {
    const m = {};
    for (const c of cameras) m[c.id] = c;
    return m;
  }, [cameras]);

  // ── CRUD ────────────────────────────────────────────────────────────────
  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setModalError("");
    setShowModal(true);
  };

  const openEdit = (g) => {
    setEditingId(g.id);
    setForm({
      name: g.name,
      description: g.description || "",
      is_facial_active: g.is_facial_active,
      is_lpr_active: g.is_lpr_active,
    });
    setModalError("");
    setShowModal(true);
  };

  const submitForm = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setModalError("Le nom du groupe est obligatoire.");
      return;
    }
    setSubmitting(true);
    setModalError("");
    try {
      const url = editingId ? `/api/groups/${editingId}` : "/api/groups";
      const method = editingId ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setModalError(data?.message || "Échec de l'enregistrement.");
        return;
      }
      setShowModal(false);
      await loadAll();
    } catch {
      setModalError("Erreur réseau.");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteGroup = async (g) => {
    if (!window.confirm(`Supprimer le groupe « ${g.name} » ? Les caméras ne sont pas supprimées.`)) return;
    setBusyId(g.id);
    try {
      const res = await fetch(`/api/groups/${g.id}`, { method: "DELETE" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        window.alert(d?.message || "Échec de la suppression.");
        return;
      }
      await loadAll();
    } finally {
      setBusyId(null);
    }
  };

  // ── Bascule de module en masse (PATCH /modules) ─────────────────────────
  const toggleModule = async (g, key) => {
    const next = !g[key];
    setBusyId(g.id);
    // Optimiste : reflète immédiatement dans l'UI.
    setGroups((prev) => prev.map((x) => (x.id === g.id ? { ...x, [key]: next } : x)));
    try {
      const res = await fetch(`/api/groups/${g.id}/modules`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: next }),
      });
      if (!res.ok) {
        // Rollback en cas d'échec.
        setGroups((prev) => prev.map((x) => (x.id === g.id ? { ...x, [key]: !next } : x)));
        const d = await res.json().catch(() => ({}));
        window.alert(d?.message || "Échec de la bascule.");
      }
    } catch {
      setGroups((prev) => prev.map((x) => (x.id === g.id ? { ...x, [key]: !next } : x)));
    } finally {
      setBusyId(null);
    }
  };

  // ── Membres (add / remove caméra) ───────────────────────────────────────
  const toggleMembership = async (group, camera, isMember) => {
    const url = `/api/groups/${group.id}/cameras/${camera.id}`;
    const res = await fetch(url, { method: isMember ? "DELETE" : "POST" });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      window.alert(d?.message || "Échec de la mise à jour de l'appartenance.");
      return;
    }
    const updated = await res.json().catch(() => null);
    if (updated) {
      setGroups((prev) => prev.map((x) => (x.id === group.id ? updated : x)));
      setMembersGroup((prev) => (prev && prev.id === group.id ? updated : prev));
    }
    // Rafraîchit les caméras (group_ids / config effective).
    fetch("/api/cameras").then((r) => (r.ok ? r.json() : [])).then(setCameras).catch(() => {});
  };

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      {/* Modal création / édition */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingId ? "Modifier le groupe" : "Nouveau groupe"}
              </h2>
              <button onClick={() => setShowModal(false)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <svg className="h-5 w-5 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form onSubmit={submitForm} className="p-6 space-y-4">
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
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Périmètre extérieur"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Description</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="Caméras du parking et des accès"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ModuleSwitch
                  label="Facial"
                  active={form.is_facial_active}
                  onClick={() => setForm((f) => ({ ...f, is_facial_active: !f.is_facial_active }))}
                />
                <ModuleSwitch
                  label="LPR / Plaques"
                  active={form.is_lpr_active}
                  onClick={() => setForm((f) => ({ ...f, is_lpr_active: !f.is_lpr_active }))}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  Annuler
                </button>
                <button type="submit" disabled={submitting} className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-medium transition-colors shadow-lg shadow-blue-500/30">
                  {submitting ? "Enregistrement..." : editingId ? "Enregistrer" : "Créer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal gestion des membres */}
      {membersGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Caméras du groupe</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">{membersGroup.name}</p>
              </div>
              <button onClick={() => setMembersGroup(null)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <svg className="h-5 w-5 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4 max-h-[60vh] overflow-y-auto space-y-1.5">
              {cameras.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400 p-4 text-center">Aucune caméra disponible.</p>
              )}
              {cameras.map((cam) => {
                const isMember = (membersGroup.camera_ids || []).includes(cam.id);
                return (
                  <div key={cam.id} className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{cam.cam_name}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{cam.location || "—"}</p>
                    </div>
                    <button
                      disabled={!canWrite}
                      onClick={() => toggleMembership(membersGroup, cam, isMember)}
                      className={`shrink-0 ml-3 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                        isMember
                          ? "bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100"
                          : "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 hover:bg-blue-100"
                      }`}
                    >
                      {isMember ? "Retirer" : "Ajouter"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="flex min-h-screen">
        <AdminSidebar
          currentRole={currentRole}
          isCollapsed={isCollapsed}
          onToggle={() => setIsCollapsed((p) => !p)}
          currentPath="/Osirion/admin/groups"
        />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Groupes de caméras"
            subtitle={`${groups.length} groupe(s) • bascule de module en masse (appliquée à chaud)`}
            showSearch={false}
            actions={
              canWrite ? (
                <button onClick={openCreate} className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors shadow-lg shadow-blue-500/30 inline-flex items-center gap-2">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 5v14M5 12h14" /></svg>
                  Nouveau groupe
                </button>
              ) : null
            }
          />

          <div className="px-6 lg:px-10 py-8">
            {loading ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">Chargement…</p>
            ) : error ? (
              <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">{error}</div>
            ) : groups.length === 0 ? (
              <div className="text-center py-20">
                <p className="text-gray-500 dark:text-gray-400">Aucun groupe pour le moment.</p>
                {canWrite && (
                  <button onClick={openCreate} className="mt-4 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium">
                    Créer le premier groupe
                  </button>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {groups.map((g) => (
                  <div key={g.id} className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm p-5 flex flex-col">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="text-base font-semibold text-gray-900 dark:text-white truncate">{g.name}</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2">{g.description || "—"}</p>
                      </div>
                      <span className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                        {g.camera_count ?? (g.camera_ids || []).length} 📹
                      </span>
                    </div>

                    {/* Bascules de module */}
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <ModuleToggleCard
                        label="Facial"
                        active={g.is_facial_active}
                        disabled={!canWrite || busyId === g.id}
                        onClick={() => toggleModule(g, "is_facial_active")}
                      />
                      <ModuleToggleCard
                        label="LPR"
                        active={g.is_lpr_active}
                        disabled={!canWrite || busyId === g.id}
                        onClick={() => toggleModule(g, "is_lpr_active")}
                      />
                    </div>

                    {/* Aperçu des caméras membres */}
                    {(g.camera_ids || []).length > 0 && (
                      <div className="mt-4 flex flex-wrap gap-1.5">
                        {(g.camera_ids || []).slice(0, 4).map((cid) => (
                          <span key={cid} className="text-[11px] px-2 py-0.5 rounded-md bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-100 dark:border-gray-700">
                            {camerasById[cid]?.cam_name || `#${cid}`}
                          </span>
                        ))}
                        {(g.camera_ids || []).length > 4 && (
                          <span className="text-[11px] px-2 py-0.5 rounded-md text-gray-500">+{(g.camera_ids || []).length - 4}</span>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="mt-auto pt-5 flex items-center gap-2">
                      <button
                        onClick={() => setMembersGroup(g)}
                        className="flex-1 px-3 py-2 rounded-lg text-sm font-medium bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      >
                        Caméras
                      </button>
                      {canWrite && (
                        <>
                          <button onClick={() => openEdit(g)} className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" title="Modifier">
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                          </button>
                          <button onClick={() => deleteGroup(g)} disabled={busyId === g.id} className="p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50" title="Supprimer">
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /></svg>
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

// Interrupteur de module dans le formulaire (état local).
function ModuleSwitch({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center justify-between px-3 py-2.5 rounded-xl border text-sm font-medium transition-colors ${
        active
          ? "border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300"
          : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-500"
      }`}
    >
      <span>{label}</span>
      <span className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${active ? "bg-emerald-500" : "bg-gray-300 dark:bg-gray-600"}`}>
        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${active ? "translate-x-4" : "translate-x-1"}`} />
      </span>
    </button>
  );
}

// Carte-bascule d'un module directement sur la fiche du groupe.
function ModuleToggleCard({ label, active, disabled, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex flex-col items-start gap-1 px-3 py-2.5 rounded-xl border transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
        active
          ? "border-emerald-300 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20"
          : "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
      }`}
    >
      <span className={`text-xs font-medium ${active ? "text-emerald-700 dark:text-emerald-300" : "text-gray-500"}`}>{label}</span>
      <span className={`text-sm font-semibold ${active ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400"}`}>
        {active ? "Actif" : "Coupé"}
      </span>
    </button>
  );
}

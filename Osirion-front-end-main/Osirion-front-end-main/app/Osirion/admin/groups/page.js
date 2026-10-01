"use client";

/**
 * Groupes de caméras (sites / agences) — section Configurer (thème clair).
 * CRUD + gestion des membres (caméras d'un groupe). Design aligné sur la plateforme
 * (tokens os-*). Consomme /api/groups/* et /api/cameras.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { Plus, X, Pencil, Trash2, Layers, Video } from "lucide-react";
import { useAuth } from "../AuthContext";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, EmptyState } from "../_osirion/ui";

const EMPTY_FORM = { name: "", description: "" };

export default function GroupsPage() {
  const [groups, setGroups] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");
  const [membersGroup, setMembersGroup] = useState(null);

  const user = useAuth();
  const canWrite = ["admin", "user"].includes(user?.role || "viewer");

  const loadAll = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [gr, cr] = await Promise.all([fetch("/api/groups"), fetch("/api/cameras")]);
      if (!gr.ok) throw new Error("groups");
      setGroups((await gr.json()) || []);
      setCameras(cr.ok ? (await cr.json()) || [] : []);
    } catch { setError("Erreur lors du chargement des groupes."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { loadAll(); }, [loadAll]);

  const camerasById = useMemo(() => { const m = {}; for (const c of cameras) m[c.id] = c; return m; }, [cameras]);

  const openCreate = () => { setEditingId(null); setForm(EMPTY_FORM); setModalError(""); setShowModal(true); };
  const openEdit = (g) => { setEditingId(g.id); setForm({ name: g.name, description: g.description || "" }); setModalError(""); setShowModal(true); };

  const submitForm = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setModalError("Le nom du groupe est obligatoire."); return; }
    setSubmitting(true); setModalError("");
    try {
      const res = await fetch(editingId ? `/api/groups/${editingId}` : "/api/groups", {
        method: editingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setModalError(data?.message || "Échec de l'enregistrement."); return; }
      setShowModal(false); await loadAll();
    } catch { setModalError("Erreur réseau."); }
    finally { setSubmitting(false); }
  };

  const deleteGroup = async (g) => {
    if (!window.confirm(`Supprimer le groupe « ${g.name} » ? Les caméras ne sont pas supprimées.`)) return;
    setBusyId(g.id);
    try {
      const res = await fetch(`/api/groups/${g.id}`, { method: "DELETE" });
      if (!res.ok) { const d = await res.json().catch(() => ({})); window.alert(d?.message || "Échec de la suppression."); return; }
      await loadAll();
    } finally { setBusyId(null); }
  };

  const toggleMembership = async (group, camera, isMember) => {
    const res = await fetch(`/api/groups/${group.id}/cameras/${camera.id}`, { method: isMember ? "DELETE" : "POST" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); window.alert(d?.message || "Échec de la mise à jour de l'appartenance."); return; }
    const updated = await res.json().catch(() => null);
    if (updated) {
      setGroups((prev) => prev.map((x) => (x.id === group.id ? updated : x)));
      setMembersGroup((prev) => (prev && prev.id === group.id ? updated : prev));
    }
    fetch("/api/cameras").then((r) => (r.ok ? r.json() : [])).then(setCameras).catch(() => {});
  };

  const inp = "w-full px-3.5 py-2.5 rounded-os border border-os-border bg-os-card text-[14px] text-os-t1 outline-none focus:border-os-t3";
  const lbl = "block text-[13px] font-semibold text-os-t1 mb-1.5";

  return (
    <OsShell>
      {/* Modal création / édition */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-os-lg border border-os-border bg-os-card shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-os-border">
              <h2 className="text-[16px] font-semibold text-os-t1">{editingId ? "Modifier le groupe" : "Nouveau groupe"}</h2>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-os text-os-t3 hover:text-os-t1 hover:bg-os-card-2"><X className="h-5 w-5" /></button>
            </div>
            <form onSubmit={submitForm} className="p-5 space-y-4">
              {modalError && <div className="px-3.5 py-2.5 rounded-os border border-os-border bg-os-card-2 text-[13px] text-os-red">{modalError}</div>}
              <div>
                <label className={lbl}>Nom <span className="text-os-red">*</span></label>
                <input type="text" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Agence Niamey" className={inp} />
              </div>
              <div>
                <label className={lbl}>Description</label>
                <input type="text" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="Caméras de l'agence et des accès" className={inp} />
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 rounded-os border border-os-border text-[13px] font-medium text-os-t2 hover:text-os-t1">Annuler</button>
                <button type="submit" disabled={submitting} className="flex-1 px-4 py-2.5 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover disabled:opacity-60">
                  {submitting ? "Enregistrement…" : editingId ? "Enregistrer" : "Créer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal gestion des membres */}
      {membersGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setMembersGroup(null)}>
          <div className="w-full max-w-lg rounded-os-lg border border-os-border bg-os-card shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-os-border">
              <div>
                <h2 className="text-[16px] font-semibold text-os-t1">Caméras du groupe</h2>
                <p className="text-[13px] text-os-t3">{membersGroup.name}</p>
              </div>
              <button onClick={() => setMembersGroup(null)} className="p-1.5 rounded-os text-os-t3 hover:text-os-t1 hover:bg-os-card-2"><X className="h-5 w-5" /></button>
            </div>
            <div className="p-4 max-h-[60vh] overflow-y-auto space-y-1.5">
              {cameras.length === 0 && <p className="text-[13px] text-os-t3 p-4 text-center">Aucune caméra disponible.</p>}
              {cameras.map((cam) => {
                const isMember = (membersGroup.camera_ids || []).includes(cam.id);
                return (
                  <div key={cam.id} className="flex items-center justify-between px-3.5 py-2.5 rounded-os border border-os-border hover:bg-os-card-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-os-t1 truncate">{cam.cam_name}</p>
                      <p className="text-[11px] text-os-t3 truncate">{cam.location || "—"}</p>
                    </div>
                    <button disabled={!canWrite} onClick={() => toggleMembership(membersGroup, cam, isMember)}
                      className={`shrink-0 ml-3 px-3 py-1.5 rounded-os text-[12px] font-medium disabled:opacity-50 border ${
                        isMember ? "border-transparent bg-os-card-2 text-os-red hover:text-white hover:bg-os-red" : "border-transparent bg-os-cta text-white hover:bg-os-cta-hover"
                      }`}>
                      {isMember ? "Retirer" : "Ajouter"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="p-6">
        <PageHeader
          title="Groupes de caméras"
          subtitle={`${groups.length} groupe(s) · organisation du parc par site / agence`}
          actions={canWrite ? (
            <button onClick={openCreate} className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover inline-flex items-center gap-2">
              <Plus className="h-4 w-4" /> Nouveau groupe
            </button>
          ) : null}
        />

        {loading ? (
          <EmptyState icon={Layers}>Chargement…</EmptyState>
        ) : error ? (
          <Card className="p-4"><p className="text-[13px] text-os-red">{error}</p></Card>
        ) : groups.length === 0 ? (
          <EmptyState icon={Layers}>Aucun groupe pour le moment.{canWrite ? " Créez-en un pour organiser votre parc." : ""}</EmptyState>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {groups.map((g) => {
              const ids = g.camera_ids || [];
              return (
                <Card key={g.id} className="p-5 flex flex-col">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-[15px] font-semibold text-os-t1 truncate">{g.name}</h3>
                      <p className="text-[13px] text-os-t3 line-clamp-2">{g.description || "—"}</p>
                    </div>
                    <span className="shrink-0 inline-flex items-center gap-1 os-num text-[12px] font-medium px-2.5 py-1 rounded-full bg-os-card-2 border border-os-border-2 text-os-t2">
                      <Video className="h-3.5 w-3.5" /> {g.camera_count ?? ids.length}
                    </span>
                  </div>

                  {ids.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {ids.slice(0, 4).map((cid) => (
                        <span key={cid} className="text-[11px] px-2 py-0.5 rounded-os bg-os-card-2 text-os-t2 border border-os-border-2">
                          {camerasById[cid]?.cam_name || `#${cid}`}
                        </span>
                      ))}
                      {ids.length > 4 && <span className="text-[11px] px-2 py-0.5 rounded-os text-os-t4">+{ids.length - 4}</span>}
                    </div>
                  )}

                  <div className="mt-auto pt-5 flex items-center gap-2">
                    <button onClick={() => setMembersGroup(g)} className="flex-1 px-3 py-2 rounded-os text-[13px] font-medium border border-os-border text-os-t2 hover:text-os-t1">Caméras</button>
                    {canWrite && (
                      <>
                        <button onClick={() => openEdit(g)} title="Modifier" className="p-2 rounded-os text-os-t3 hover:text-os-t1 hover:bg-os-card-2"><Pencil className="h-4 w-4" /></button>
                        <button onClick={() => deleteGroup(g)} disabled={busyId === g.id} title="Supprimer" className="p-2 rounded-os text-os-red hover:bg-os-card-2 disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>
                      </>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </OsShell>
  );
}

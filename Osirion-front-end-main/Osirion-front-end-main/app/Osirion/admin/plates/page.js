"use client";

import { useState, useMemo, useEffect } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { Car, Plus, Search, ShieldAlert, ShieldCheck, Pencil, Trash2, X, ScanLine } from "lucide-react";

const EMPTY_FORM = { plate_text: "", owner_name: "", notes: "", is_blacklisted: false };

export default function PlatesPage() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("tous"); // tous | blacklist | known
  const [plates, setPlates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [modalForm, setModalForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");

  // Outil de test du fuzzy matching OCR
  const [testInput, setTestInput] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const user = useAuth();
  const currentRole = user?.role || "viewer";
  const canWrite = ["admin", "user"].includes(currentRole);

  const fetchPlates = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/plates", { headers: { "Content-Type": "application/json" } });
      if (!res.ok) {
        setError("Erreur lors de la récupération des plaques.");
        return;
      }
      setPlates((await res.json()) || []);
    } catch {
      setError("Erreur réseau.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPlates(); }, []);

  const filteredPlates = useMemo(() => {
    return plates.filter((p) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        q === "" ||
        p.plate_text?.toLowerCase().includes(q) ||
        p.owner_name?.toLowerCase().includes(q) ||
        String(p.id).includes(q);
      const matchesStatus =
        statusFilter === "tous" ||
        (statusFilter === "blacklist" && p.is_blacklisted) ||
        (statusFilter === "known" && !p.is_blacklisted);
      return matchesSearch && matchesStatus;
    });
  }, [plates, searchQuery, statusFilter]);

  const counts = useMemo(() => ({
    tous: plates.length,
    blacklist: plates.filter((p) => p.is_blacklisted).length,
    withOwner: plates.filter((p) => p.owner_name).length,
  }), [plates]);

  const openAdd = () => { setEditingId(null); setModalForm(EMPTY_FORM); setModalError(""); setShowModal(true); };
  const openEdit = (p) => {
    setEditingId(p.id);
    setModalForm({
      plate_text: p.plate_text || "",
      owner_name: p.owner_name || "",
      notes: p.notes || "",
      is_blacklisted: !!p.is_blacklisted,
    });
    setModalError("");
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setModalError("");
    try {
      const url = editingId ? `/api/plates/${editingId}` : "/api/plates";
      const method = editingId ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(modalForm),
      });
      const data = await res.json();
      if (!res.ok) {
        setModalError(data?.message || "Erreur lors de l'enregistrement.");
        return;
      }
      setShowModal(false);
      setModalForm(EMPTY_FORM);
      setEditingId(null);
      await fetchPlates();
    } catch {
      setModalError("Erreur réseau.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Supprimer cette plaque ?")) return;
    try {
      const res = await fetch(`/api/plates/${id}`, { method: "DELETE" });
      if (res.ok) setPlates((prev) => prev.filter((p) => p.id !== id));
    } catch {}
  };

  const handleToggleBlacklist = async (p) => {
    const next = !p.is_blacklisted;
    try {
      const res = await fetch(`/api/plates/${p.id}/blacklist?blacklisted=${next}`, { method: "POST" });
      if (res.ok) {
        setPlates((prev) => prev.map((x) => (x.id === p.id ? { ...x, is_blacklisted: next } : x)));
      }
    } catch {}
  };

  const runTest = async (e) => {
    e.preventDefault();
    if (!testInput.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/plates/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plate_text: testInput, threshold: 0.82, k: 1 }),
      });
      const data = await res.json();
      setTestResult(res.ok ? data : { error: data?.message || "Erreur" });
    } catch {
      setTestResult({ error: "Erreur réseau." });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      {/* Modal ajout / édition */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingId ? "Modifier la plaque" : "Ajouter une plaque"}
              </h2>
              <button onClick={() => setShowModal(false)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <X className="h-5 w-5 text-gray-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {modalError && (
                <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
                  {modalError}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Plaque <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={modalForm.plate_text}
                  onChange={(e) => setModalForm((f) => ({ ...f, plate_text: e.target.value }))}
                  placeholder="1-ABC 234"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm font-mono uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  Normalisée automatiquement (majuscules, sans espaces ni tirets).
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Propriétaire</label>
                <input
                  type="text"
                  value={modalForm.owner_name}
                  onChange={(e) => setModalForm((f) => ({ ...f, owner_name: e.target.value }))}
                  placeholder="Nom du propriétaire"
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Notes</label>
                <input
                  type="text"
                  value={modalForm.notes}
                  onChange={(e) => setModalForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="Marque, modèle, remarque..."
                  className="w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setModalForm((f) => ({ ...f, is_blacklisted: !f.is_blacklisted }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${modalForm.is_blacklisted ? "bg-red-600" : "bg-gray-300 dark:bg-gray-600"}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${modalForm.is_blacklisted ? "translate-x-6" : "translate-x-1"}`} />
                </button>
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {modalForm.is_blacklisted ? "Sur liste de surveillance (blacklist)" : "Véhicule normal"}
                </span>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  Annuler
                </button>
                <button type="submit" disabled={submitting} className="flex-1 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-medium transition-colors shadow-lg shadow-blue-500/30">
                  {submitting ? "Enregistrement..." : editingId ? "Enregistrer" : "Ajouter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="flex min-h-screen">
        <AdminSidebar currentRole={currentRole} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/plates" />

        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar
            title="Gestion des plaques"
            subtitle={`${counts.tous} véhicule(s) • ${counts.blacklist} sous surveillance`}
            showSearch={false}
            actions={
              canWrite && (
                <button onClick={openAdd} className="rounded-xl bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-blue-500/30">
                  <Plus className="h-4 w-4" /> Ajouter une plaque
                </button>
              )
            }
          />

          {/* Stats */}
          <div className="px-6 lg:px-10 py-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 p-5 border border-gray-200/50 dark:border-gray-700/50">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Total véhicules</div>
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">{counts.tous}</div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-gray-400 to-gray-600 flex items-center justify-center"><Car className="h-6 w-6 text-white" /></div>
                </div>
              </div>
              <div className="rounded-2xl bg-gradient-to-br from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 p-5 border border-red-200/50 dark:border-red-700/50">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wider mb-2">Sous surveillance</div>
                    <div className="text-3xl font-bold text-red-700 dark:text-red-400">{counts.blacklist}</div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-red-400 to-red-600 flex items-center justify-center"><ShieldAlert className="h-6 w-6 text-white" /></div>
                </div>
              </div>
              <div className="rounded-2xl bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 p-5 border border-emerald-200/50 dark:border-emerald-700/50">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-2">Propriétaire renseigné</div>
                    <div className="text-3xl font-bold text-emerald-700 dark:text-emerald-400">{counts.withOwner}</div>
                  </div>
                  <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center"><ShieldCheck className="h-6 w-6 text-white" /></div>
                </div>
              </div>
            </div>
          </div>

          {/* Outil de test fuzzy OCR */}
          <div className="px-6 lg:px-10 pb-2">
            <div className="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
              <div className="flex items-center gap-2 mb-3">
                <ScanLine className="h-5 w-5 text-indigo-500" />
                <h3 className="text-sm font-bold text-gray-900 dark:text-white">Tester la recherche floue (OCR)</h3>
              </div>
              <form onSubmit={runTest} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  placeholder="Simuler une lecture OCR, ex. 1ABC234 ou 1ABCZ34"
                  className="flex-1 px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl text-sm font-mono uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:text-white"
                />
                <button type="submit" disabled={testing} className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-medium transition-colors">
                  {testing ? "Recherche..." : "Rechercher"}
                </button>
              </form>
              {testResult && (
                <div className="mt-3 text-sm">
                  {testResult.error ? (
                    <span className="text-red-600 dark:text-red-400">{testResult.error}</span>
                  ) : testResult.matched ? (
                    <div className="px-4 py-3 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
                      <span className="text-emerald-700 dark:text-emerald-300">
                        Correspondance : <b className="font-mono">{testResult.results[0].plate_text}</b>
                        {" "}— score {Number(testResult.results[0].score).toFixed(3)}
                        {testResult.results[0].is_blacklisted && <span className="ml-2 text-red-600 dark:text-red-400 font-semibold">[BLACKLIST]</span>}
                        {testResult.results[0].owner_name ? ` — ${testResult.results[0].owner_name}` : ""}
                      </span>
                    </div>
                  ) : (
                    <div className="px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400">
                      Aucune correspondance pour <b className="font-mono">{testResult.query}</b> (seuil 0.82).
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Filtres + recherche */}
          <div className="px-6 lg:px-10 py-5">
            <div className="flex flex-col lg:flex-row gap-4">
              <div className="flex-1 relative group">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400 group-focus-within:text-blue-500 transition-colors" />
                <input
                  type="text"
                  placeholder="Rechercher par plaque, propriétaire ou ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:text-white transition-all"
                />
              </div>
              <div className="flex gap-2">
                {[
                  { value: "tous", label: "Tous", count: counts.tous },
                  { value: "blacklist", label: "Blacklist", count: counts.blacklist },
                  { value: "known", label: "Normales", count: counts.tous - counts.blacklist },
                ].map((f) => (
                  <button
                    key={f.value}
                    onClick={() => setStatusFilter(f.value)}
                    className={`whitespace-nowrap px-4 py-2.5 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${statusFilter === f.value ? "bg-blue-600 text-white shadow-lg shadow-blue-500/30" : "bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-800"}`}
                  >
                    {f.label}
                    <span className={`px-2 py-0.5 rounded-lg text-xs font-semibold ${statusFilter === f.value ? "bg-white/20 text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"}`}>{f.count}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="px-6 lg:px-10 pb-10">
            {error && (
              <div className="mb-4 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">{error}</div>
            )}
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Plaque</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Propriétaire</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Statut</th>
                      <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Notes</th>
                      <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {loading ? (
                      <tr><td colSpan="5" className="px-6 py-16 text-center text-gray-500 dark:text-gray-400">Chargement...</td></tr>
                    ) : filteredPlates.length === 0 ? (
                      <tr>
                        <td colSpan="5" className="px-6 py-16 text-center">
                          <div className="flex flex-col items-center justify-center text-gray-500 dark:text-gray-400">
                            <Car className="h-16 w-16 mb-4 opacity-40" />
                            <p className="text-base font-medium">Aucune plaque enregistrée</p>
                            <p className="text-sm mt-1">Ajoutez un véhicule connu ou une plaque à surveiller.</p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredPlates.map((p) => (
                        <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group">
                          <td className="px-6 py-4">
                            <div className="inline-flex items-center gap-2">
                              <span className="font-mono font-bold tracking-wider text-gray-900 dark:text-white px-2.5 py-1 rounded-md bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
                                {p.plate_text}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">{p.owner_name || "—"}</td>
                          <td className="px-6 py-4">
                            {p.is_blacklisted ? (
                              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border bg-red-500/10 text-red-600 dark:bg-red-500/20 dark:text-red-400 border-red-500/20">
                                <ShieldAlert className="h-3.5 w-3.5" /> Blacklist
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400 border-emerald-500/20">
                                <ShieldCheck className="h-3.5 w-3.5" /> Normale
                              </span>
                            )}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate">{p.notes || "—"}</td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-1">
                              {canWrite && (
                                <>
                                  <button onClick={() => handleToggleBlacklist(p)} title={p.is_blacklisted ? "Retirer de la blacklist" : "Mettre en blacklist"} className="p-2 hover:bg-amber-100 dark:hover:bg-amber-900/30 rounded-lg transition-colors">
                                    <ShieldAlert className={`h-4 w-4 ${p.is_blacklisted ? "text-red-500" : "text-gray-400"}`} />
                                  </button>
                                  <button onClick={() => openEdit(p)} title="Modifier" className="p-2 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg transition-colors">
                                    <Pencil className="h-4 w-4 text-blue-500" />
                                  </button>
                                  <button onClick={() => handleDelete(p.id)} title="Supprimer" className="p-2 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors">
                                    <Trash2 className="h-4 w-4 text-red-500" />
                                  </button>
                                </>
                              )}
                              {!canWrite && <span className="text-xs text-gray-400">Lecture seule</span>}
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
    </div>
  );
}

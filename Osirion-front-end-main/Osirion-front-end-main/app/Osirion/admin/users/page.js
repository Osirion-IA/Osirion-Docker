"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { useAuth } from "../AuthContext";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Banner } from "../_osirion/ui";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "@/app/lib/fetchWithRefresh";
import { getSetting } from "@/app/lib/settings";

// ── Constantes rôles ────────────────────────────────────────────────────────

const ROLE_CONFIG = {
  admin: {
    label: "Administrateur",
    styles: "text-os-red",
  },
  user: {
    label: "Utilisateur",
    styles: "text-os-blue",
  },
  viewer: {
    label: "Observateur",
    styles: "bg-os-card-2 text-os-t2",
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatRelative(d) {
  if (!d) return "Jamais";
  const diff = Date.now() - new Date(d).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (minutes < 60) return `Il y a ${minutes} min`;
  if (hours < 24) return `Il y a ${hours}h`;
  if (days < 7) return `Il y a ${days}j`;
  return formatDate(d);
}

// ── Composants UI ──────────────────────────────────────────────────────────

function Avatar({ name }) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
  return (
    <div className="h-11 w-11 rounded-os bg-os-card-2 border border-os-border-2 flex items-center justify-center flex-shrink-0">
      <span className="os-num text-os-t2 font-semibold text-sm">{initials}</span>
    </div>
  );
}

function RoleBadge({ role }) {
  const cfg = ROLE_CONFIG[role] ?? {
    label: role,
    styles: "bg-os-card-2 text-os-t2",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-os text-xs font-semibold ${cfg.styles}`}>
      {cfg.label}
    </span>
  );
}

function StatusBadge({ isActive }) {
  return isActive ? (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-os text-xs font-semibold text-os-green">
      <span className="h-1.5 w-1.5 rounded-full bg-os-green" />
      Actif
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-os text-xs font-semibold bg-os-card-2 text-os-t2">
      <span className="h-1.5 w-1.5 rounded-full bg-os-t4" />
      Inactif
    </span>
  );
}

// ── Overlay modal ──────────────────────────────────────────────────────────

function ModalOverlay({ children, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

function ModalCard({ title, onClose, children }) {
  return (
    <div className="bg-os-card rounded-os-lg border border-os-border p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-os-t1">{title}</h2>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-black/5 rounded-os transition-colors"
        >
          <svg className="h-5 w-5 text-os-t3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-os-t2 mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  "w-full px-3.5 py-2.5 rounded-os border border-os-border bg-os-card-2 focus:outline-none focus:ring-os-t3 text-sm text-os-t1";

const selectCls =
  "w-full px-3.5 py-2.5 rounded-os border border-os-border bg-os-card-2 focus:outline-none focus:ring-os-t3 text-sm text-os-t1";

// ── Modal : Créer un utilisateur ───────────────────────────────────────────

function CreateUserModal({ onClose, onSuccess }) {
  const [form, setForm] = useState({
    fullName: "",
    email: "",
    password: "",
    role: "viewer",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Longueur minimale de mot de passe : paramètre Sécurité (défaut 8).
  const pwdMin = Number(getSetting("passwordMinLength", 8)) || 8;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.password.length < pwdMin) {
      setError(`Le mot de passe doit contenir au moins ${pwdMin} caractères.`);
      return;
    }
    setLoading(true);
    try {
      const res = await fetchWithRefresh("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        setError(data.message || "Erreur lors de la création.");
        return;
      }
      onSuccess();
    } catch {
      setError("Erreur réseau.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <ModalCard title="Nouvel utilisateur" onClose={onClose}>
        {error && <Banner message={error} className="mb-4" />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Nom complet">
            <input
              type="text"
              required
              value={form.fullName}
              onChange={set("fullName")}
              className={inputCls}
              placeholder="Jean Dupont"
            />
          </Field>
          <Field label="Email">
            <input
              type="email"
              required
              value={form.email}
              onChange={set("email")}
              className={inputCls}
              placeholder="jean@exemple.com"
            />
          </Field>
          <Field label="Mot de passe">
            <input
              type="password"
              required
              minLength={pwdMin}
              value={form.password}
              onChange={set("password")}
              className={inputCls}
              placeholder={`Min. ${pwdMin} car., 1 maj., 1 chiffre`}
            />
          </Field>
          <Field label="Rôle">
            <select value={form.role} onChange={set("role")} className={selectCls}>
              <option value="viewer">Observateur</option>
              <option value="user">Utilisateur</option>
              <option value="admin">Administrateur</option>
            </select>
          </Field>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-os border border-os-border text-sm font-medium hover:bg-black/5 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2.5 rounded-os bg-os-card text-white text-sm font-medium hover:bg-black/5 transition-colors disabled:opacity-50"
            >
              {loading ? "Création..." : "Créer"}
            </button>
          </div>
        </form>
      </ModalCard>
    </ModalOverlay>
  );
}

// ── Modal : Modifier un utilisateur ───────────────────────────────────────

function EditUserModal({ user, onClose, onSuccess }) {
  const [form, setForm] = useState({
    fullName: user.fullName,
    email: user.email,
    role: user.role,
    is_active: user.is_active,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetchWithRefresh(`/api/users/${user.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        setError(data.message || "Erreur lors de la mise à jour.");
        return;
      }
      onSuccess();
    } catch {
      setError("Erreur réseau.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <ModalCard title="Modifier l'utilisateur" onClose={onClose}>
        {error && <Banner message={error} className="mb-4" />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Nom complet">
            <input
              type="text"
              required
              value={form.fullName}
              onChange={set("fullName")}
              className={inputCls}
            />
          </Field>
          <Field label="Email">
            <input
              type="email"
              required
              value={form.email}
              onChange={set("email")}
              className={inputCls}
            />
          </Field>
          <Field label="Rôle">
            <select value={form.role} onChange={set("role")} className={selectCls}>
              <option value="viewer">Observateur</option>
              <option value="user">Utilisateur</option>
              <option value="admin">Administrateur</option>
            </select>
          </Field>
          <div className="flex items-center justify-between px-4 py-3 rounded-os bg-os-card-2 border border-os-border">
            <span className="text-sm font-medium text-os-t2">
              Compte actif
            </span>
            <button
              type="button"
              onClick={() => setForm((f) => ({ ...f, is_active: !f.is_active }))}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                form.is_active ? "bg-os-green" : "bg-os-border-2"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  form.is_active ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-os border border-os-border text-sm font-medium hover:bg-black/5 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2.5 rounded-os bg-os-card text-white text-sm font-medium hover:bg-black/5 transition-colors disabled:opacity-50"
            >
              {loading ? "Enregistrement..." : "Enregistrer"}
            </button>
          </div>
        </form>
      </ModalCard>
    </ModalOverlay>
  );
}

// ── Modal : Confirmer la suppression ──────────────────────────────────────

function DeleteUserModal({ user, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleDelete = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await fetchWithRefresh(`/api/users/${user.id}`, {
        method: "DELETE",
      });
      if (!res) return;
      if (!res.ok) {
        const data = await res.json();
        setError(data.message || "Erreur lors de la suppression.");
        return;
      }
      onSuccess();
    } catch {
      setError("Erreur réseau.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-os-card rounded-os-lg border border-os-border p-6 shadow-xl">
        <div className="flex flex-col items-center text-center mb-6">
          <div className="h-14 w-14 rounded-os-lg flex items-center justify-center mb-4">
            <svg className="h-7 w-7 text-os-red" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-os-t1">
            Supprimer l'utilisateur
          </h2>
          <p className="mt-2 text-sm text-os-t3">
            Êtes-vous sûr de vouloir supprimer{" "}
            <span className="font-medium text-os-t1">
              {user.fullName}
            </span>{" "}
            ? Cette action est irréversible.
          </p>
        </div>
        {error && <Banner message={error} className="mb-4" />}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-os border border-os-border text-sm font-medium hover:bg-black/5 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={handleDelete}
            disabled={loading}
            className="flex-1 px-4 py-2.5 rounded-os bg-os-red text-white text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {loading ? "Suppression..." : "Supprimer"}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ── Page principale ────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("tous");
  const [statusFilter, setStatusFilter] = useState("tous");

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editUser, setEditUser] = useState(null);
  const [deleteUser, setDeleteUser] = useState(null);

  const auth = useAuth();
  const currentRole = auth?.role || "viewer";
  const isAdmin = currentRole === "admin";

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchWithRefresh("/api/users");
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        setError(data.message || "Impossible de charger les utilisateurs.");
        return;
      }
      setUsers(data);
    } catch {
      setError("Erreur réseau.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        q === "" ||
        u.fullName.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q);
      const matchesRole = roleFilter === "tous" || u.role === roleFilter;
      const matchesStatus =
        statusFilter === "tous" ||
        (statusFilter === "actif" && u.is_active) ||
        (statusFilter === "inactif" && !u.is_active);
      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchQuery, roleFilter, statusFilter]);

  const stats = useMemo(
    () => ({
      total: users.length,
      actifs: users.filter((u) => u.is_active).length,
      admins: users.filter((u) => u.role === "admin").length,
      utilisateurs: users.filter((u) => u.role === "user").length,
      viewers: users.filter((u) => u.role === "viewer").length,
    }),
    [users]
  );

  const colSpan = isAdmin ? 6 : 5;

  if (auth && !["admin"].includes(auth.role)) {
    return (
      <OsShell>
        <div className="p-6"><AccessDenied role={auth.role} /></div>
      </OsShell>
    );
  }

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader
          title="Utilisateurs & rôles"
          subtitle={`${stats.total} utilisateur(s) · ${stats.actifs} actif(s) · ${stats.admins} admin(s)`}
          actions={
            <>
              <button onClick={fetchUsers} className="px-3.5 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1">Actualiser</button>
              {isAdmin && (
                <button onClick={() => setShowCreateModal(true)} className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover inline-flex items-center gap-2">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                  Ajouter un utilisateur
                </button>
              )}
            </>
          }
        />

          <div>
            {/* Statistiques */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard
                label="Total"
                value={stats.total}
                iconColor="gray"
                icon={
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                }
                iconExtra={
                  <>
                    <circle cx="9" cy="7" r="4" />
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                  </>
                }
              />
              <StatCard
                label="Administrateurs"
                value={stats.admins}
                iconColor="red"
                icon={
                  <>
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
                  </>
                }
              />
              <StatCard
                label="Utilisateurs"
                value={stats.utilisateurs}
                iconColor="blue"
                icon={
                  <>
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                  </>
                }
              />
              <StatCard
                label="Observateurs"
                value={stats.viewers}
                iconColor="gray"
                icon={
                  <>
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </>
                }
              />
            </div>

            {/* Filtres */}
            <div className="bg-os-card rounded-os-lg border border-os-border p-4 mb-6">
              <div className="flex flex-col lg:flex-row gap-4">
                {/* Recherche */}
                <div className="flex-1 relative">
                  <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 h-5 w-5 text-os-t4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Rechercher un utilisateur..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-11 pr-4 py-2.5 rounded-os border border-os-border bg-os-card-2 focus:outline-none focus:ring-os-t3 text-sm"
                  />
                </div>

                {/* Filtre rôle */}
                <div className="flex gap-2 flex-wrap">
                  {[
                    { label: "Tous", value: "tous", count: stats.total },
                    { label: "Admin", value: "admin", count: stats.admins },
                    { label: "Utilisateur", value: "user", count: stats.utilisateurs },
                    { label: "Observateur", value: "viewer", count: stats.viewers },
                  ].map((f) => (
                    <button
                      key={f.value}
                      onClick={() => setRoleFilter(f.value)}
                      className={`px-4 py-2 rounded-os text-sm font-medium transition-all flex items-center gap-2 ${
                        roleFilter === f.value
                          ? "bg-os-primary text-os-on-primary shadow-lg"
                          : "bg-os-card text-os-t2 hover:bg-black/5 border border-os-border"
                      }`}
                    >
                      {f.label}
                      <span
                        className={`px-2 py-0.5 rounded-os text-xs font-semibold ${
                          roleFilter === f.value
                            ? "bg-os-card text-white"
                            : "bg-os-card-2 text-os-t3"
                        }`}
                      >
                        {f.count}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Filtre statut */}
                <div className="flex gap-2">
                  {[
                    { label: "Tous", value: "tous" },
                    { label: "Actifs", value: "actif" },
                    { label: "Inactifs", value: "inactif" },
                  ].map((f) => (
                    <button
                      key={f.value}
                      onClick={() => setStatusFilter(f.value)}
                      className={`px-4 py-2 rounded-os text-sm font-medium transition-all ${
                        statusFilter === f.value
                          ? "bg-os-card text-white"
                          : "bg-os-card text-os-t2 hover:bg-black/5 border border-os-border"
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Table */}
            <div className="bg-os-card rounded-os-lg border border-os-border overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center py-20">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 rounded-full border-2 border-os-t2 border-t-transparent animate-spin" />
                    <p className="text-sm text-os-t3">
                      Chargement des utilisateurs...
                    </p>
                  </div>
                </div>
              ) : error ? (
                <div className="flex items-center justify-center py-20">
                  <div className="flex flex-col items-center gap-3 text-center">
                    <svg className="h-12 w-12 text-os-red opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v4M12 16h.01" />
                    </svg>
                    <p className="text-sm text-os-red">{error}</p>
                    <button
                      onClick={fetchUsers}
                      className="text-sm font-medium text-os-blue hover:underline"
                    >
                      Réessayer
                    </button>
                  </div>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead className="bg-os-card-2 border-b border-os-border">
                      <tr>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3 uppercase tracking-wider">
                          Utilisateur
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3 uppercase tracking-wider">
                          Rôle
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3 uppercase tracking-wider">
                          Statut
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3 uppercase tracking-wider">
                          Dernière connexion
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-os-t3 uppercase tracking-wider">
                          Créé le
                        </th>
                        {isAdmin && (
                          <th className="px-6 py-4 text-right text-xs font-semibold text-os-t3 uppercase tracking-wider">
                            Actions
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-os-border">
                      {filteredUsers.length === 0 ? (
                        <tr>
                          <td colSpan={colSpan} className="px-6 py-16 text-center">
                            <div className="flex flex-col items-center gap-2 text-os-t3">
                              <svg className="h-16 w-16 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                                <circle cx="9" cy="7" r="4" />
                                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
                              </svg>
                              <p className="text-base font-medium">Aucun utilisateur trouvé</p>
                              <p className="text-sm">Essayez de modifier vos critères de recherche</p>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        filteredUsers.map((u) => (
                          <tr
                            key={u.id}
                            className="hover:bg-black/5 transition-colors group"
                          >
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                <Avatar name={u.fullName} />
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-os-t1 truncate">
                                    {u.fullName}
                                  </div>
                                  <div className="text-xs text-os-t3 mt-0.5 truncate">
                                    {u.email}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <RoleBadge role={u.role} />
                            </td>
                            <td className="px-6 py-4">
                              <StatusBadge isActive={u.is_active} />
                            </td>
                            <td className="px-6 py-4">
                              <span className="text-sm text-os-t3">
                                {formatRelative(u.last_login)}
                              </span>
                            </td>
                            <td className="px-6 py-4">
                              <span className="text-sm text-os-t3">
                                {formatDate(u.created_at)}
                              </span>
                            </td>
                            {isAdmin && (
                              <td className="px-6 py-4">
                                <div className="flex items-center justify-end gap-1">
                                  <button
                                    onClick={() => setEditUser(u)}
                                    title="Modifier"
                                    className="p-2 hover:bg-black/5 rounded-os transition-colors opacity-0 group-hover:opacity-100"
                                  >
                                    <svg className="h-4 w-4 text-os-t3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                                    </svg>
                                  </button>
                                  <button
                                    onClick={() => setDeleteUser(u)}
                                    title="Supprimer"
                                    className="p-2 hover:bg-black/5 rounded-os transition-colors opacity-0 group-hover:opacity-100"
                                  >
                                    <svg className="h-4 w-4 text-os-red" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                    </svg>
                                  </button>
                                </div>
                              </td>
                            )}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateUserModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            fetchUsers();
          }}
        />
      )}
      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSuccess={() => {
            setEditUser(null);
            fetchUsers();
          }}
        />
      )}
      {deleteUser && (
        <DeleteUserModal
          user={deleteUser}
          onClose={() => setDeleteUser(null)}
          onSuccess={() => {
            setDeleteUser(null);
            fetchUsers();
          }}
        />
      )}
    </OsShell>
  );
}

// ── Composant carte statistique ────────────────────────────────────────────

function StatCard({ label, value, iconColor, icon, iconExtra }) {
  const colorMap = {
    gray: {
      bg: "bg-os-card-2",
      icon: "text-os-t3",
    },
    red: {
      bg: "",
      icon: "text-os-red",
    },
    blue: {
      bg: "",
      icon: "text-os-blue",
    },
  };
  const colors = colorMap[iconColor] ?? colorMap.gray;

  return (
    <div className="bg-os-card rounded-os-lg border border-os-border p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-os-t3 font-medium">{label}</p>
          <p className="text-3xl font-bold text-os-t1 mt-2">{value}</p>
        </div>
        <div className={`h-12 w-12 rounded-os ${colors.bg} flex items-center justify-center`}>
          <svg className={`h-6 w-6 ${colors.icon}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {icon}
            {iconExtra}
          </svg>
        </div>
      </div>
    </div>
  );
}

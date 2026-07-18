"use client";

/**
 * Moteur de règles — SI un événement satisfait des conditions PENDANT une plage
 * horaire ALORS créer une alerte (+ notifier). Ex. intrusion horaire :
 * trigger « Occupation de zone », zone armée, min 1 personne, plage 22h–6h, email.
 */
import { useState, useEffect, useCallback } from "react";
import AdminSidebar from "../AdminSidebar";
import AdminTopBar from "../AdminTopBar";
import { useAuth } from "../AuthContext";
import { AccessDenied } from "../RoleGuard";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const TRIGGERS = [
  { value: "ZONE_OCCUPANCY_CHANGED", label: "Occupation de zone", cond: "count" },
  { value: "CROWD_DETECTED", label: "Attroupement", cond: "count" },
  { value: "LINE_CROSSED", label: "Franchissement de ligne", cond: "direction" },
  { value: "ZONE_DWELL", label: "Temps de présence", cond: "wait" },
];
const KINDS = ["intrusion", "crowd", "queue", "custom"];
const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]; // index = weekday() (0=lundi)
const triggerLabel = (v) => TRIGGERS.find((t) => t.value === v)?.label || v;
const triggerCond = (v) => TRIGGERS.find((t) => t.value === v)?.cond;

const EMPTY = {
  name: "", trigger: "ZONE_OCCUPANCY_CHANGED", zone_id: "", kind: "intrusion",
  min_count: "", min_wait_s: "", direction: "any",
  days: [], from: "", to: "", notify_email: false, notify_webhook: false,
};

export default function RulesPage() {
  const user = useAuth();
  const role = user?.role || "viewer";
  const canWrite = ["admin", "user"].includes(role);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const [rules, setRules] = useState([]);
  const [zones, setZones] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [r, z] = await Promise.all([
      fetchWithRefresh("/api/rules"),
      fetchWithRefresh("/api/zones"),
    ]);
    setRules(r?.ok ? await r.json() : []);
    setZones(z?.ok ? await z.json() : []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleDay = (i) => setForm((f) => ({
    ...f, days: f.days.includes(i) ? f.days.filter((d) => d !== i) : [...f.days, i].sort(),
  }));

  const save = async () => {
    setMsg("");
    if (!form.name.trim()) { setMsg("Nom requis."); return; }
    const cond = triggerCond(form.trigger);
    const conditions = {};
    if (cond === "count" && form.min_count !== "") conditions.min_count = Number(form.min_count);
    if (cond === "wait" && form.min_wait_s !== "") conditions.min_wait_s = Number(form.min_wait_s);
    if (cond === "direction" && form.direction && form.direction !== "any") conditions.direction = form.direction;

    let schedule = null;
    if (form.days.length || form.from || form.to) {
      schedule = {};
      if (form.days.length) schedule.days = form.days;
      if (form.from) schedule.from = form.from;
      if (form.to) schedule.to = form.to;
    }
    const notify_channels = [];
    if (form.notify_email) notify_channels.push("email");
    if (form.notify_webhook) notify_channels.push("webhook");

    const payload = {
      name: form.name.trim(),
      trigger: form.trigger,
      zone_id: (cond === "direction" || form.zone_id === "") ? null : Number(form.zone_id),
      kind: form.kind,
      conditions: Object.keys(conditions).length ? conditions : null,
      schedule,
      notify_channels,
    };
    const res = await fetchWithRefresh("/api/rules", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!res?.ok) { setMsg("Échec de l'enregistrement."); return; }
    setForm(EMPTY);
    load();
  };

  const toggleActive = async (r) => {
    await fetchWithRefresh(`/api/rules/${r.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !r.is_active }),
    });
    load();
  };
  const del = async (id) => { await fetchWithRefresh(`/api/rules/${id}`, { method: "DELETE" }); load(); };

  const scheduleTxt = (s) => {
    if (!s) return "toujours";
    const d = (s.days || []).map((i) => DAYS[i]).join(" ");
    const h = s.from || s.to ? `${s.from || "00:00"}–${s.to || "23:59"}` : "";
    return [d, h].filter(Boolean).join(" ") || "toujours";
  };
  const condTxt = (c) => {
    if (!c) return "—";
    return Object.entries(c).map(([k, v]) => `${k}=${v}`).join(", ");
  };

  if (user && !["admin", "user", "viewer"].includes(role)) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)]">
        <div className="flex min-h-screen">
          <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/rules" />
          <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}><AccessDenied role={role} /></main>
        </div>
      </div>
    );
  }

  const cond = triggerCond(form.trigger);

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="flex min-h-screen">
        <AdminSidebar currentRole={role} isCollapsed={isCollapsed} onToggle={() => setIsCollapsed((p) => !p)} currentPath="/Osirion/admin/rules" />
        <main className={`flex-1 transition-all duration-400 ${isCollapsed ? "lg:ml-20" : "lg:ml-80"}`}>
          <AdminTopBar title="Règles & alertes" subtitle="Déclenchez alertes et notifications sur les événements (intrusion, attroupement, saturation)" showSearch={false} />

          <div className="p-6 grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* Formulaire */}
            {canWrite && (
              <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 space-y-3">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Nouvelle règle</h3>

                <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Nom (ex. Intrusion nuit — entrée)"
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />

                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs text-gray-500 dark:text-gray-400">Déclencheur
                    <select value={form.trigger} onChange={(e) => set("trigger", e.target.value)}
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white">
                      {TRIGGERS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </label>
                  <label className="text-xs text-gray-500 dark:text-gray-400">Type d&apos;alerte
                    <select value={form.kind} onChange={(e) => set("kind", e.target.value)}
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white">
                      {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </label>
                </div>

                {cond !== "direction" && (
                  <label className="text-xs text-gray-500 dark:text-gray-400 block">Zone (optionnel)
                    <select value={form.zone_id} onChange={(e) => set("zone_id", e.target.value)}
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white">
                      <option value="">Toutes les zones</option>
                      {zones.map((z) => <option key={z.id} value={z.id}>{z.name} (cam {z.camera_id})</option>)}
                    </select>
                  </label>
                )}

                {/* Condition selon le déclencheur */}
                {cond === "count" && (
                  <label className="text-xs text-gray-500 dark:text-gray-400 block">Occupation minimale (personnes)
                    <input type="number" min="1" value={form.min_count} onChange={(e) => set("min_count", e.target.value)} placeholder="ex. 1 (intrusion) / 5 (attroupement)"
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                  </label>
                )}
                {cond === "wait" && (
                  <label className="text-xs text-gray-500 dark:text-gray-400 block">Temps de présence minimal (secondes)
                    <input type="number" min="1" value={form.min_wait_s} onChange={(e) => set("min_wait_s", e.target.value)} placeholder="ex. 300 (5 min)"
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                  </label>
                )}
                {cond === "direction" && (
                  <label className="text-xs text-gray-500 dark:text-gray-400 block">Sens
                    <select value={form.direction} onChange={(e) => set("direction", e.target.value)}
                      className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white">
                      <option value="any">Peu importe</option>
                      <option value="in">Entrée</option>
                      <option value="out">Sortie</option>
                    </select>
                  </label>
                )}

                {/* Plage horaire armée */}
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Plage horaire armée (vide = toujours)</p>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {DAYS.map((d, i) => (
                      <button key={i} type="button" onClick={() => toggleDay(i)}
                        className={`px-2 py-1 rounded-md text-xs ${form.days.includes(i) ? "bg-indigo-600 text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"}`}>{d}</button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="time" value={form.from} onChange={(e) => set("from", e.target.value)}
                      className="px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                    <span className="text-gray-400 text-sm">→</span>
                    <input type="time" value={form.to} onChange={(e) => set("to", e.target.value)}
                      className="px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white" />
                    <span className="text-[11px] text-gray-400">(22:00 → 06:00 gère la nuit)</span>
                  </div>
                </div>

                {/* Notifications */}
                <div className="flex items-center gap-4 text-sm text-gray-700 dark:text-gray-300">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Notifier :</span>
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={form.notify_email} onChange={(e) => set("notify_email", e.target.checked)} /> Email</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={form.notify_webhook} onChange={(e) => set("notify_webhook", e.target.checked)} /> Webhook</label>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <button onClick={save} className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600 hover:bg-emerald-700 text-white">Créer la règle</button>
                  {msg && <span className="text-sm text-rose-600 dark:text-rose-400">{msg}</span>}
                </div>
              </div>
            )}

            {/* Liste */}
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Règles ({rules.length})</h3>
              {rules.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">Aucune règle. Créez-en une (ex. intrusion nuit).</p>
              ) : (
                <ul className="space-y-3">
                  {rules.map((r) => (
                    <li key={r.id} className="rounded-xl border border-gray-100 dark:border-gray-800 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                            {r.name} <span className="text-xs font-normal text-gray-400">· {r.kind}</span>
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                            {triggerLabel(r.trigger)} · cond {condTxt(r.conditions)} · {scheduleTxt(r.schedule)}
                            {r.notify_channels?.length ? ` · notif ${r.notify_channels.join("/")}` : ""}
                          </p>
                        </div>
                        {canWrite && (
                          <div className="flex items-center gap-2 shrink-0">
                            <button onClick={() => toggleActive(r)}
                              className={`text-xs px-2 py-1 rounded-md ${r.is_active ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" : "bg-gray-100 text-gray-500 dark:bg-gray-800"}`}>
                              {r.is_active ? "Active" : "Inactive"}
                            </button>
                            <button onClick={() => del(r.id)} className="text-xs text-rose-600 hover:underline">Suppr.</button>
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-gray-400 mt-4">
                Astuce intrusion : déclencheur « Occupation de zone », zone armée, occupation min 1,
                plage 22:00 → 06:00, notifier Email. Les alertes apparaissent dans « Alertes ».
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

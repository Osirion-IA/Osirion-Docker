"use client";

/**
 * Règles & alertes — section Configurer (thème clair). Crée des règles métier
 * (scénario → déclencheur, zone, seuil/condition, plage, sévérité, temporisation,
 * notification) + panneau des règles actives avec bascules. Données /api/rules.
 */
import { useState, useEffect, useCallback } from "react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card, Banner } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const TRIGGERS = [
  { value: "ZONE_OCCUPANCY_CHANGED", label: "Occupation de zone", cond: "count" },
  { value: "CROWD_DETECTED", label: "Attroupement", cond: "count" },
  { value: "LINE_CROSSED", label: "Franchissement de ligne", cond: "direction" },
  { value: "ZONE_DWELL", label: "Temps de présence", cond: "wait" },
  // Signal temps réel : l'épisode a dépassé la tolérance du régime. La durée
  // finale POST_ABSENCE sert aux statistiques, pas à attendre avant d'alerter.
  { value: "POST_VACANT", label: "Poste vacant", cond: "none" },
  { value: "STAFFING_LOW", label: "Effectif sous le minimum", cond: "none" },
];
const KINDS = ["intrusion", "crowd", "queue", "absence", "staffing", "custom"];
const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];
const SEV = { info: { label: "Info", color: "var(--os-blue)" }, warning: { label: "Warning", color: "var(--os-amber)" }, critical: { label: "Critique", color: "var(--os-red)" } };
const SEV_ORDER = ["info", "warning", "critical"];
const GROUP_TRIGGERS = new Set(["POST_VACANT", "STAFFING_LOW"]);
const triggerLabel = (v) => TRIGGERS.find((t) => t.value === v)?.label || v;
const triggerCond = (v) => TRIGGERS.find((t) => t.value === v)?.cond;
const FIELD_FR = { count: "occupation", dwell_s: "attente(s)", direction: "sens" };
const predTxt = (p) => `${FIELD_FR[p.field] || p.field} ${p.op} ${p.value}`;

const EMPTY = {
  name: "", trigger: "ZONE_OCCUPANCY_CHANGED", zone_id: "", kind: "intrusion", severity: "warning",
  work_schedule_id: "",
  min_count: "", max_count: "", min_wait_s: "", direction: "any",
  days: [], from: "", to: "", cooldown_min: "", notify_email: false, notify_webhook: false,
};
const TEMPLATES = [
  { key: "intrusion_nuit", label: "Intrusion nocturne", form: { name: "Intrusion nocturne", trigger: "ZONE_OCCUPANCY_CHANGED", kind: "intrusion", severity: "critical", min_count: "1", days: ALL_DAYS, from: "22:00", to: "06:00", cooldown_min: "5", notify_email: true } },
  { key: "saturation_file", label: "Saturation de file", form: { name: "Saturation de file d'attente", trigger: "CROWD_DETECTED", kind: "queue", severity: "warning", min_count: "5", cooldown_min: "2", notify_email: true } },
  { key: "attroupement", label: "Attroupement", form: { name: "Attroupement anormal", trigger: "CROWD_DETECTED", kind: "crowd", severity: "warning", min_count: "8", cooldown_min: "2" } },
  { key: "stationnement", label: "Stationnement prolongé", form: { name: "Stationnement prolongé", trigger: "ZONE_DWELL", kind: "custom", severity: "info", min_wait_s: "300", cooldown_min: "5" } },
  { key: "zone_interdite", label: "Zone interdite", form: { name: "Accès zone interdite", trigger: "ZONE_OCCUPANCY_CHANGED", kind: "intrusion", severity: "critical", min_count: "1", cooldown_min: "5", notify_email: true } },
  { key: "poste_vacant", label: "Poste vacant", form: { name: "Poste d'agent vacant", trigger: "POST_VACANT", kind: "absence", severity: "warning", cooldown_min: "30", notify_email: true } },
  { key: "sous_effectif", label: "Sous-effectif", form: { name: "Effectif agents insuffisant", trigger: "STAFFING_LOW", kind: "staffing", severity: "critical", cooldown_min: "30", notify_email: true } },
];

export default function RulesPage() {
  const user = useAuth();
  const canWrite = ["admin", "user"].includes(user?.role);
  const [rules, setRules] = useState([]);
  const [zones, setZones] = useState([]);
  const [workSchedules, setWorkSchedules] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [r, z, w] = await Promise.all([
      fetchWithRefresh("/api/rules"), fetchWithRefresh("/api/zones"),
      fetchWithRefresh("/api/work-schedules?active_only=true"),
    ]);
    setRules(r?.ok ? await r.json() : []);
    setZones(z?.ok ? await z.json() : []);
    setWorkSchedules(w?.ok ? await w.json() : []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setTrigger = (value) => setForm((current) => ({
    ...current,
    trigger: value,
    work_schedule_id: GROUP_TRIGGERS.has(value) ? current.work_schedule_id : "",
  }));
  const toggleDay = (i) => setForm((f) => ({ ...f, days: f.days.includes(i) ? f.days.filter((d) => d !== i) : [...f.days, i].sort() }));
  const applyTemplate = (t) => { setMsg(""); setForm({ ...EMPTY, ...t.form }); };

  const save = async () => {
    setMsg("");
    if (!form.name.trim()) { setMsg("Nom requis."); return; }
    const cond = triggerCond(form.trigger);
    let conditions = null;
    if (cond === "count") {
      const preds = [];
      if (form.min_count !== "") preds.push({ field: "count", op: ">=", value: Number(form.min_count) });
      if (form.max_count !== "") preds.push({ field: "count", op: "<=", value: Number(form.max_count) });
      if (preds.length) conditions = { all: preds };
    } else if (cond === "wait" && form.min_wait_s !== "") {
      conditions = { all: [{ field: "dwell_s", op: ">=", value: Number(form.min_wait_s) }] };
    } else if (cond === "direction" && form.direction && form.direction !== "any") {
      conditions = { all: [{ field: "direction", op: "==", value: form.direction }] };
    }
    const grouped = GROUP_TRIGGERS.has(form.trigger) && form.work_schedule_id !== "";
    let schedule = null;
    if (!grouped && (form.days.length || form.from || form.to)) {
      schedule = {};
      if (form.days.length) schedule.days = form.days;
      if (form.from) schedule.from = form.from;
      if (form.to) schedule.to = form.to;
    }
    const notify_channels = [];
    if (form.notify_email) notify_channels.push("email");
    if (form.notify_webhook) notify_channels.push("webhook");
    const payload = {
      name: form.name.trim(), trigger: form.trigger,
      zone_id: (cond === "direction" || form.trigger === "STAFFING_LOW" || form.zone_id === "") ? null : Number(form.zone_id),
      work_schedule_id: grouped ? Number(form.work_schedule_id) : null,
      kind: form.kind, severity: form.severity,
      cooldown_s: form.cooldown_min !== "" ? Math.round(Number(form.cooldown_min) * 60) : 0,
      conditions, schedule, notify_channels,
    };
    const res = await fetchWithRefresh("/api/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res?.ok) { setMsg("Échec de l'enregistrement."); return; }
    setForm(EMPTY); load();
  };
  const toggleActive = async (r) => { await fetchWithRefresh(`/api/rules/${r.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: !r.is_active }) }); load(); };
  const del = async (id) => { await fetchWithRefresh(`/api/rules/${id}`, { method: "DELETE" }); load(); };

  const scheduleTxt = (s) => { if (!s) return "en permanence"; const d = (s.days || []).map((i) => DAYS[i]).join(" "); const h = s.from || s.to ? `${s.from || "00:00"}–${s.to || "23:59"}` : ""; return [d, h].filter(Boolean).join(" ") || "en permanence"; };
  const condTxt = (c) => { if (!c) return "—"; if (Array.isArray(c.all)) return c.all.map(predTxt).join(" et "); if (Array.isArray(c.any)) return c.any.map(predTxt).join(" ou "); return Object.entries(c).map(([k, v]) => `${k}=${v}`).join(", "); };
  const cooldownTxt = (s) => (!s ? null : s % 60 === 0 ? `${s / 60} min` : `${s}s`);
  const scheduleName = (id) => workSchedules.find((item) => Number(item.id) === Number(id))?.name || `Groupe ${id}`;

  const cond = triggerCond(form.trigger);
  const groupSelected = GROUP_TRIGGERS.has(form.trigger) && form.work_schedule_id !== "";
  const inp = "w-full px-3 py-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1 outline-none focus:border-os-t3";
  const lbl = "text-[11px] font-semibold tracking-wide uppercase text-os-t4";

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader title="Règles & alertes" subtitle="Créez des règles" />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          {canWrite && (
            <Card className="p-5 space-y-3.5">
              <h3 className="text-[15px] font-semibold text-os-t1">Nouvelle règle</h3>

              <div>
                <p className={`${lbl} mb-1.5`}>Partir d&apos;un scénario</p>
                <div className="flex flex-wrap gap-1.5">
                  {TEMPLATES.map((t) => (
                    <button key={t.key} type="button" onClick={() => applyTemplate(t)}
                      className="px-2.5 py-1.5 rounded-os text-[12px] border border-os-border bg-os-card text-os-t2 hover:text-os-t1 hover:border-os-t3">
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Nom (ex. Intrusion nuit — entrée)" className={inp} />

              <div className="grid grid-cols-2 gap-3">
                <label className={lbl}>Déclencheur
                  <select value={form.trigger} onChange={(e) => setTrigger(e.target.value)} className={`${inp} mt-1`}>
                    {TRIGGERS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </label>
                <label className={lbl}>Type d&apos;alerte
                  <select value={form.kind} onChange={(e) => set("kind", e.target.value)} className={`${inp} mt-1`}>
                    {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                </label>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className={lbl}>Sévérité
                  <select value={form.severity} onChange={(e) => set("severity", e.target.value)} className={`${inp} mt-1`}>
                    {SEV_ORDER.map((s) => <option key={s} value={s}>{SEV[s].label}</option>)}
                  </select>
                </label>
                <label className={lbl}>Temporisation (min)
                  <input type="number" min="0" value={form.cooldown_min} onChange={(e) => set("cooldown_min", e.target.value)} placeholder="0 = chaque événement" className={`${inp} mt-1`} />
                </label>
              </div>

              {cond !== "direction" && form.trigger !== "STAFFING_LOW" && (
                <label className={`${lbl} block`}>Zone (optionnel)
                  <select value={form.zone_id} onChange={(e) => set("zone_id", e.target.value)} className={`${inp} mt-1`}>
                    <option value="">Toutes les zones</option>
                    {zones.map((z) => <option key={z.id} value={z.id}>{z.name} (cam {z.camera_id})</option>)}
                  </select>
                </label>
              )}

              {GROUP_TRIGGERS.has(form.trigger) && (
                <label className={`${lbl} block`}>Groupe horaire (optionnel)
                  <select value={form.work_schedule_id} onChange={(e) => set("work_schedule_id", e.target.value)} className={`${inp} mt-1`}>
                    <option value="">Tous les groupes</option>
                    {workSchedules.map((schedule) => <option key={schedule.id} value={schedule.id}>{schedule.name} · {schedule.zones_count} poste(s)</option>)}
                  </select>
                  <span className="normal-case tracking-normal font-normal block mt-1 text-[10px] text-os-t4">La règle s&apos;applique à toutes les caméras utilisant ce régime. Les jours, heures et pauses sont hérités du groupe.</span>
                </label>
              )}

              {cond === "count" && (
                <div className="grid grid-cols-2 gap-3">
                  <label className={`${lbl} block`}>Occupation min.
                    <input type="number" min="1" value={form.min_count} onChange={(e) => set("min_count", e.target.value)} placeholder="ex. 1 / 5" className={`${inp} mt-1`} />
                  </label>
                  <label className={`${lbl} block`}>Occupation max.
                    <input type="number" min="1" value={form.max_count} onChange={(e) => set("max_count", e.target.value)} placeholder="borne haute" className={`${inp} mt-1`} />
                  </label>
                </div>
              )}
              {cond === "wait" && (
                <label className={`${lbl} block`}>Présence minimale (s)
                  <input type="number" min="1" value={form.min_wait_s} onChange={(e) => set("min_wait_s", e.target.value)} placeholder="ex. 300" className={`${inp} mt-1`} />
                </label>
              )}
              {cond === "direction" && (
                <label className={`${lbl} block`}>Sens
                  <select value={form.direction} onChange={(e) => set("direction", e.target.value)} className={`${inp} mt-1`}>
                    <option value="any">Peu importe</option><option value="in">Entrée</option><option value="out">Sortie</option>
                  </select>
                </label>
              )}

              {!groupSelected && <div>
                <p className={`${lbl} mb-1.5`}>Plage horaire armée (vide = toujours)</p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {DAYS.map((d, i) => (
                    <button key={i} type="button" onClick={() => toggleDay(i)}
                      className={`px-2 py-1 rounded-os text-[12px] ${form.days.includes(i) ? "bg-os-cta text-white" : "border border-os-border text-os-t3"}`}>{d}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <input type="time" value={form.from} onChange={(e) => set("from", e.target.value)} className={`${inp} !w-auto`} />
                  <span className="text-os-t4">→</span>
                  <input type="time" value={form.to} onChange={(e) => set("to", e.target.value)} className={`${inp} !w-auto`} />
                  <span className="text-[11px] text-os-t4">(22:00 → 06:00 = nuit)</span>
                </div>
              </div>}
              {groupSelected && (
                <div className="rounded-os border border-os-blue/25 bg-os-blue/5 px-3 py-2 text-[11px] text-os-t2">
                  Horaire armé hérité de « {scheduleName(form.work_schedule_id)} » — toute modification du groupe sera appliquée automatiquement.
                </div>
              )}

              <div className="flex items-center gap-4 text-[13px] text-os-t2">
                <span className={lbl}>Notifier :</span>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={form.notify_email} onChange={(e) => set("notify_email", e.target.checked)} /> Email</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={form.notify_webhook} onChange={(e) => set("notify_webhook", e.target.checked)} /> Webhook</label>
              </div>

              <div className="flex items-center gap-3 pt-1">
                <button onClick={save} className="px-4 py-2.5 rounded-os text-[13px] font-semibold bg-os-cta text-white hover:bg-os-cta-hover">Créer la règle</button>
                {msg && <Banner message={msg} />}
              </div>
            </Card>
          )}

          <Card className="p-5">
            <h3 className="text-[15px] font-semibold text-os-t1 mb-3">Règles actives ({rules.length})</h3>
            {rules.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-6 text-center">Aucune règle. Partez d&apos;un scénario (ex. Intrusion nocturne).</p>
            ) : (
              <ul className="space-y-2.5">
                {rules.map((r) => {
                  const sev = SEV[r.severity] || SEV.warning;
                  const cd = cooldownTxt(r.cooldown_s);
                  return (
                    <li key={r.id} className="rounded-os border border-os-border p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-semibold uppercase tracking-wide inline-flex items-center gap-1" style={{ color: sev.color }}><span className="h-1.5 w-1.5 rounded-full" style={{ background: sev.color }} />{sev.label}</span>
                            <p className="text-[13px] font-semibold text-os-t1 truncate">{r.name}</p>
                          </div>
                          <p className="text-[12px] text-os-t3 mt-1">
                            {triggerLabel(r.trigger)} · {condTxt(r.conditions)} · {r.work_schedule_id ? `groupe ${scheduleName(r.work_schedule_id)}` : scheduleTxt(r.schedule)}{cd ? ` · ⏲ ${cd}` : ""}
                            {r.notify_channels?.length ? ` · ${r.notify_channels.join("/")}` : ""}
                          </p>
                          <p className="os-num text-[11px] text-os-t4 mt-0.5">{r.trigger_count || 0} déclenchement{(r.trigger_count || 0) > 1 ? "s" : ""}</p>
                        </div>
                        {canWrite && (
                          <div className="flex items-center gap-2 shrink-0">
                            <button onClick={() => toggleActive(r)} title={r.is_active ? "Désactiver" : "Activer"}
                              className={`relative h-5 w-9 rounded-full transition-colors ${r.is_active ? "bg-os-green" : "bg-os-border-2"}`}>
                              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${r.is_active ? "left-[18px]" : "left-0.5"}`} />
                            </button>
                            <button onClick={() => del(r.id)} className="text-[12px] text-os-red hover:underline">Suppr.</button>
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </OsShell>
  );
}

"use client";
/**
 * Régimes horaires — jours, créneaux de travail, fuseau et tolérance d'absence.
 *
 * Un régime est partagé par N zones de présence : le modifier se répercute sur
 * toutes les caméras concernées. L'écran l'affiche en clair (« appliqué à N
 * postes ») avant toute modification ou suppression.
 *
 * Les PAUSES ne sont pas saisies séparément : un jour est une liste de créneaux
 * travaillés, et une pause est simplement le trou entre deux créneaux. Le même
 * modèle gère les demi-journées et les horaires coupés.
 */
import { useCallback, useEffect, useState } from "react";
import { Clock, Plus, Trash2, Copy, AlertTriangle } from "lucide-react";
import { Card, EmptyState } from "./ui";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const JOURS = [
  { cle: "0", nom: "Lundi", court: "Lun" },
  { cle: "1", nom: "Mardi", court: "Mar" },
  { cle: "2", nom: "Mercredi", court: "Mer" },
  { cle: "3", nom: "Jeudi", court: "Jeu" },
  { cle: "4", nom: "Vendredi", court: "Ven" },
  { cle: "5", nom: "Samedi", court: "Sam" },
  { cle: "6", nom: "Dimanche", court: "Dim" },
];

// Fuseaux du réseau. Attention : « Africa/Cotonou » N'EXISTE PAS dans la base
// IANA — le Bénin, c'est « Africa/Porto-Novo ».
const FUSEAUX = [
  { value: "Africa/Niamey", label: "Niger — Niamey (UTC+1)" },
  { value: "Africa/Porto-Novo", label: "Bénin — Porto-Novo / Cotonou (UTC+1)" },
  { value: "Africa/Accra", label: "Ghana — Accra (UTC+0)" },
  { value: "Africa/Lome", label: "Togo — Lomé (UTC+0)" },
  { value: "Africa/Bamako", label: "Mali — Bamako (UTC+0)" },
];

const MODELE_H24 = () => ({
  0: [["00:00", "00:00"]],
  1: [["00:00", "00:00"]],
  2: [["00:00", "00:00"]],
  3: [["00:00", "00:00"]],
  4: [["00:00", "13:00"], ["14:00", "00:00"]],
  5: [["00:00", "00:00"]],
  6: [["00:00", "00:00"]],
});

const REGIME_VIERGE = () => ({
  name: "",
  description: "Activité 24 h/24 · pause prière le vendredi de 13 h à 14 h",
  timezone: "Africa/Niamey",
  absence_tolerance_s: 600,
  segments: MODELE_H24(),
});

const inp = "px-2.5 py-1.5 rounded-os border border-os-border bg-os-card text-[13px] text-os-t1 outline-none focus:border-os-t3";
const lbl = "block text-[13px] font-semibold text-os-t1 mb-1.5";

/** Heures travaillées dans la journée, en clair (« 8 h ce jour-là »). */
function heuresDuJour(creneaux) {
  const mins = (creneaux || []).reduce((total, [d, f]) => {
    const [hd, md] = String(d).split(":").map(Number);
    const [hf, mf] = String(f).split(":").map(Number);
    const debut = hd * 60 + md, fin = hf * 60 + mf;
    return total + (fin > debut ? fin - debut : fin < debut ? (24 * 60 - debut) + fin : debut === 0 ? 24 * 60 : 0);
  }, 0);
  if (!mins) return "repos";
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
}

export default function WorkSchedules({ canWrite }) {
  const [regimes, setRegimes] = useState([]);
  const [edite, setEdite] = useState(null);      // régime en cours d'édition (ou création)
  const [msg, setMsg] = useState("");
  const [chargement, setChargement] = useState(true);

  const charger = useCallback(async () => {
    setChargement(true);
    const r = await fetchWithRefresh("/api/work-schedules");
    if (r?.ok) {
      const d = await r.json();
      setRegimes(Array.isArray(d) ? d : []);
    }
    setChargement(false);
  }, []);

  useEffect(() => { charger(); }, [charger]);

  const majCreneau = (jour, idx, borne, valeur) => {
    setEdite((e) => {
      const seg = { ...e.segments };
      const jours = (seg[jour] || []).map((c, i) => (i === idx ? [...c] : c));
      jours[idx][borne] = valeur;
      seg[jour] = jours;
      return { ...e, segments: seg };
    });
  };

  const ajouterCreneau = (jour) => setEdite((e) => ({
    ...e,
    segments: { ...e.segments, [jour]: [...(e.segments[jour] || []), ["14:00", "17:00"]] },
  }));

  const retirerCreneau = (jour, idx) => setEdite((e) => ({
    ...e,
    segments: { ...e.segments, [jour]: (e.segments[jour] || []).filter((_, i) => i !== idx) },
  }));

  const appliquerModeleH24 = () => setEdite((e) => ({
    ...e,
    segments: MODELE_H24(),
  }));

  const enregistrer = async () => {
    setMsg("");
    if (!edite.name?.trim()) { setMsg("Le nom du régime est requis."); return; }
    const corps = {
      name: edite.name.trim(),
      description: edite.description || null,
      timezone: edite.timezone,
      absence_tolerance_s: Number(edite.absence_tolerance_s),
      segments: edite.segments,
    };
    const creation = !edite.id;
    const r = await fetchWithRefresh(
      creation ? "/api/work-schedules" : `/api/work-schedules/${edite.id}`,
      { method: creation ? "POST" : "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) },
    );
    if (!r?.ok) {
      const d = await r?.json().catch(() => null);
      // Le backend renvoie soit un detail texte (409), soit la liste de
      // validation Pydantic (422) — on affiche le message utile dans les deux cas.
      const det = d?.detail;
      setMsg(Array.isArray(det) ? det[0]?.msg?.replace(/^Value error, /, "") : (det || "Échec de l'enregistrement."));
      return;
    }
    setEdite(null);
    charger();
  };

  const supprimer = async (r) => {
    setMsg("");
    if (r.zones_count === 0 && !window.confirm(`Supprimer le régime « ${r.name} » ?`)) return;
    const res = await fetchWithRefresh(`/api/work-schedules/${r.id}`, { method: "DELETE" });
    if (res?.status === 409) {
      const d = await res.json().catch(() => null);
      setMsg(d?.detail || "Ce régime est encore utilisé.");
      return;
    }
    if (!res?.ok) {
      const d = await res?.json().catch(() => null);
      setMsg(d?.detail || "Impossible de supprimer ce régime.");
      return;
    }
    charger();
  };

  const basculer = async (r) => {
    setMsg("");
    if (r.is_active && r.zones_count > 0 && !window.confirm(
      `Désactiver « ${r.name} » ? Les ${r.zones_count} poste(s) associés ne seront plus surveillés jusqu'à sa réactivation.`
    )) return;
    const res = await fetchWithRefresh(`/api/work-schedules/${r.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !r.is_active }),
    });
    if (!res?.ok) {
      const d = await res?.json().catch(() => null);
      setMsg(d?.detail || "Impossible de modifier le statut du régime.");
      return;
    }
    charger();
  };

  // ── Édition ───────────────────────────────────────────────────────────────
  if (edite) {
    const nbPostes = edite.id ? (regimes.find((r) => r.id === edite.id)?.zones_count || 0) : 0;
    return (
      <Card className="p-6">
        <div className="flex items-center gap-3 mb-5">
          <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Clock className="h-5 w-5" /></span>
          <div>
            <h3 className="text-[15px] font-semibold text-os-t1">{edite.id ? "Modifier le régime" : "Nouveau régime horaire"}</h3>
            <p className="text-[13px] text-os-t3">Jours travaillés, créneaux et fuseau du groupe d&apos;agences</p>
          </div>
        </div>

        {nbPostes > 0 && (
          <p className="mb-4 px-3 py-2 rounded-os border border-os-amber/40 bg-os-amber/10 text-[13px] text-os-t2 inline-flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-os-amber shrink-0" />
            Ce régime est appliqué à <b className="mx-1">{nbPostes} poste{nbPostes > 1 ? "s" : ""}</b> — toute modification s&apos;y répercute.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2 max-w-3xl mb-6">
          <div>
            <label className={lbl}>Nom</label>
            <input value={edite.name} onChange={(e) => setEdite({ ...edite, name: e.target.value })}
              placeholder="ex. Agences Niger" className={`${inp} w-full`} />
          </div>
          <div>
            <label className={lbl}>Fuseau horaire</label>
            <select value={edite.timezone} onChange={(e) => setEdite({ ...edite, timezone: e.target.value })}
              className={`${inp} w-full`}>
              {FUSEAUX.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
            <p className="text-[12px] text-os-t3 mt-1.5">Les heures ci-dessous sont locales à ce pays.</p>
          </div>
          <div>
            <label className={lbl}>Signaler un poste vide après</label>
            <select value={edite.absence_tolerance_s}
              onChange={(e) => setEdite({ ...edite, absence_tolerance_s: Number(e.target.value) })}
              className={`${inp} w-full`}>
              {[300, 600, 900, 1800].map((s) => (
                <option key={s} value={s}>{s / 60} minutes</option>
              ))}
            </select>
          </div>
          <div>
            <label className={lbl}>Description</label>
            <input value={edite.description || ""} onChange={(e) => setEdite({ ...edite, description: e.target.value })}
              placeholder="Optionnel" className={`${inp} w-full`} />
          </div>
        </div>

        <div className="flex items-center justify-between mb-2">
          <h4 className="text-[14px] font-semibold text-os-t1">Créneaux de travail</h4>
          <button onClick={appliquerModeleH24} className="text-[12px] text-os-t2 hover:text-os-t1 inline-flex items-center gap-1.5">
            <Copy className="h-3.5 w-3.5" /> Appliquer H24 + pause vendredi
          </button>
        </div>
        <p className="text-[12px] text-os-t3 mb-3">
          <span className="os-num">00:00–00:00</span> signifie une journée complète. Le modèle par défaut surveille
          24 h/24, avec une pause le vendredi entre <span className="os-num">13:00</span> et <span className="os-num">14:00</span>.
        </p>

        <div className="space-y-2 mb-6">
          {JOURS.map((j) => {
            const creneaux = edite.segments[j.cle] || edite.segments[Number(j.cle)] || [];
            return (
              <div key={j.cle} className="flex flex-wrap items-center gap-2 rounded-os border border-os-border p-2.5">
                <span className="w-24 text-[13px] font-semibold text-os-t1 shrink-0">{j.nom}</span>
                <span className="w-16 text-[12px] text-os-t3 shrink-0">{heuresDuJour(creneaux)}</span>
                {creneaux.map((c, i) => (
                  <span key={i} className="inline-flex items-center gap-1">
                    <input type="time" value={c[0]} onChange={(e) => majCreneau(j.cle, i, 0, e.target.value)} className={`${inp} os-num`} />
                    <span className="text-os-t3">→</span>
                    <input type="time" value={c[1]} onChange={(e) => majCreneau(j.cle, i, 1, e.target.value)} className={`${inp} os-num`} />
                    <button onClick={() => retirerCreneau(j.cle, i)} title="Retirer ce créneau"
                      className="p-1 text-os-t3 hover:text-os-red"><Trash2 className="h-3.5 w-3.5" /></button>
                  </span>
                ))}
                <button onClick={() => ajouterCreneau(j.cle)}
                  className="px-2 py-1 rounded-os border border-os-border text-[12px] text-os-t2 hover:text-os-t1 inline-flex items-center gap-1">
                  <Plus className="h-3.5 w-3.5" /> Créneau
                </button>
              </div>
            );
          })}
        </div>

        {msg && <p className="text-[13px] text-os-red mb-3">{msg}</p>}
        <div className="flex items-center gap-2">
          <button onClick={enregistrer} className="px-4 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover">Enregistrer</button>
          <button onClick={() => { setEdite(null); setMsg(""); }} className="px-4 py-2 rounded-os border border-os-border text-[13px] text-os-t2 hover:text-os-t1">Annuler</button>
        </div>
      </Card>
    );
  }

  // ── Liste ─────────────────────────────────────────────────────────────────
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <span className="h-10 w-10 grid place-items-center rounded-os bg-os-card-2 border border-os-border-2 text-os-t2"><Clock className="h-5 w-5" /></span>
          <div>
            <h3 className="text-[15px] font-semibold text-os-t1">Régimes horaires</h3>
            <p className="text-[13px] text-os-t3">Jours et heures de travail par groupe d&apos;agences</p>
          </div>
        </div>
        {canWrite && (
          <button onClick={() => { setEdite(REGIME_VIERGE()); setMsg(""); }}
            className="px-3.5 py-2 rounded-os bg-os-cta text-white text-[13px] font-semibold hover:bg-os-cta-hover inline-flex items-center gap-2">
            <Plus className="h-4 w-4" /> Nouveau régime
          </button>
        )}
      </div>

      {msg && <p className="text-[13px] text-os-red mb-3">{msg}</p>}

      {chargement ? (
        <p className="text-[13px] text-os-t3">Chargement…</p>
      ) : regimes.length === 0 ? (
        <EmptyState icon={Clock}>
          Aucun régime horaire. Créez-en un par pays ou par type de poste, puis rattachez-y
          vos zones de présence lors de la configuration des caméras.
        </EmptyState>
      ) : (
        <ul className="space-y-2.5">
          {regimes.map((r) => {
            const ouvres = JOURS.filter((j) => (r.segments?.[j.cle] || []).length);
            return (
              <li key={r.id} className="flex items-center justify-between gap-3 rounded-os border border-os-border p-3">
                <div className="min-w-0">
                  <span className="block text-[13px] font-semibold text-os-t1 truncate">
                    {r.name}
                    {!r.is_active && <span className="ml-2 text-[11px] text-os-amber">désactivé</span>}
                  </span>
                  <span className="block text-[11px] text-os-t3">
                    {FUSEAUX.find((f) => f.value === r.timezone)?.label || r.timezone}
                    {" · "}{ouvres.map((j) => j.court).join(", ") || "aucun jour"}
                    {" · poste vide signalé après "}{Math.round(r.absence_tolerance_s / 60)} min
                    {" · "}{r.zones_count} poste{r.zones_count > 1 ? "s" : ""}
                  </span>
                </div>
                {canWrite && (
                  <span className="flex items-center gap-3 shrink-0">
                    <button onClick={() => basculer(r)} className="text-[12px] text-os-t2 hover:text-os-t1">
                      {r.is_active ? "Désactiver" : "Activer"}
                    </button>
                    <button onClick={() => { setEdite({ ...r }); setMsg(""); }} className="text-[12px] text-os-t2 hover:text-os-t1">Modifier</button>
                    <button onClick={() => supprimer(r)} className="text-[12px] text-os-red hover:underline">Suppr.</button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

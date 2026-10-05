"use client";

// Primitives UI Osirion — réutilisées par les écrans (tokens os-*, coins nets).
import { RefreshCw } from "lucide-react";

export function PageHeader({ title, subtitle, actions }) {
  return (
    // Sous sm, titre et actions s'empilent : côte à côte, les boutons d'action
    // (« Synchroniser HikCentral », « Ajouter une caméra »…) débordaient de
    // l'écran. `min-w-0` laisse le titre se tronquer au lieu de pousser la ligne.
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 sm:gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-[22px] font-bold text-os-t1 leading-tight">{title}</h1>
        {subtitle && <p className="text-[13px] text-os-t3 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap sm:shrink-0">{actions}</div>}
    </div>
  );
}

export function Card({ className = "", children }) {
  return <div className={`rounded-os-lg border border-os-border bg-os-card ${className}`}>{children}</div>;
}

// Contrôle segmenté (onglets, périodes 24h/7j…). value/options=[{value,label}].
export function Segmented({ value, onChange, options, size = "md" }) {
  const pad = size === "sm" ? "px-3 py-1.5 text-[12px]" : "px-3.5 py-2 text-[13px]";
  return (
    // `max-w-full` + défilement horizontal : au-delà de 3 onglets la rangée
    // dépassait la largeur du téléphone et les derniers devenaient inatteignables.
    <div className="inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-os border border-os-border bg-os-card p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            /* Onglet actif = BLEU de marque. Le libellé passe en SOMBRE
               (--os-on-primary) : du blanc sur ce bleu tomberait à 2,1:1. */
            className={`rounded-os ${pad} font-medium whitespace-nowrap transition-colors ${
              active ? "bg-os-primary text-os-on-primary" : "text-os-t3 hover:text-os-t1"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function RefreshButton({ onClick, spinning }) {
  return (
    <button
      onClick={onClick}
      className="h-9 px-3 inline-flex items-center gap-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t2 hover:text-os-t1"
    >
      <RefreshCw className={`h-4 w-4 ${spinning ? "os-anim-spin" : ""}`} /> Actualiser
    </button>
  );
}

export function EmptyState({ icon: Icon, children }) {
  return (
    <div className="py-14 text-center">
      {Icon && <Icon className="h-9 w-9 mx-auto mb-3 text-os-t4" strokeWidth={1.6} />}
      <p className="text-[13px] text-os-t3">{children}</p>
    </div>
  );
}

// ── Chargement ──────────────────────────────────────────────────────────────
// Neuf écrans affichaient neuf choses pendant le chargement : « — », un
// EmptyState « Chargement… », un spinner maison, ou rien. Ces primitives
// donnent une réponse unique, et surtout une réponse qui RÉSERVE LA PLACE :
// le contenu ne pousse plus la page quand il arrive.

/** Bloc gris animé. `w`/`h` acceptent n'importe quelle valeur CSS. */
export function Skeleton({ w = "100%", h = 14, className = "" }) {
  return <div className={`os-skeleton ${className}`} style={{ width: w, height: h }} />;
}

/** Rangée de tuiles d'indicateurs — la structure la plus fréquente en tête d'écran. */
export function SkeletonKpis({ count = 4 }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-os-lg border border-os-border bg-os-card p-5">
          <Skeleton w="45%" h={11} />
          <div className="mt-3"><Skeleton w="35%" h={26} /></div>
          <div className="mt-3"><Skeleton w="70%" h={10} /></div>
        </div>
      ))}
    </div>
  );
}

/** Lignes d'une liste ou d'un tableau. */
export function SkeletonRows({ count = 6, className = "" }) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton w={`${55 + ((i * 13) % 30)}%`} h={13} />
          <div className="ml-auto"><Skeleton w={60} h={13} /></div>
        </div>
      ))}
    </div>
  );
}

/** Carte entière en attente (titre + corps). */
export function SkeletonCard({ rows = 4, className = "" }) {
  return (
    <div className={`rounded-os-lg border border-os-border bg-os-card p-5 ${className}`}>
      <Skeleton w="30%" h={15} />
      <div className="mt-4"><SkeletonRows count={rows} /></div>
    </div>
  );
}

/**
 * Indicateur discret pour un rafraîchissement EN PLACE — quand les données
 * sont déjà à l'écran et qu'on ne veut pas les remplacer par des squelettes.
 */
export function InlineSpinner({ label = "Chargement…" }) {
  return (
    <span className="inline-flex items-center gap-2 text-[12px] text-os-t3">
      <span className="os-anim-spin h-3.5 w-3.5 rounded-full border-2 border-os-border-2 border-t-os-primary" />
      {label}
    </span>
  );
}

// ── Messages ────────────────────────────────────────────────────────────────
// Cinq rendus coexistaient : un ErrorBanner local dans Utilisateurs, un
// encadré ad hoc dans Présence, une ligne colorée dans Audit et Paramètres,
// du texte rouge sans état de succès dans Règles et Zones. Même information,
// cinq apparences — et deux écrans incapables d'annoncer une réussite.
//
// `Banner` accepte les deux formes rencontrées : une chaîne (erreur par
// défaut) ou l'objet { ok, text } déjà utilisé par Paramètres et Audit.

export function Banner({ message, tone, className = "" }) {
  if (!message) return null;
  const texte = typeof message === "string" ? message : message.text;
  if (!texte) return null;
  // `tone` explicite > champ `ok` de l'objet > erreur par défaut.
  const ok = tone ? tone === "success" : (typeof message === "object" ? !!message.ok : false);
  return (
    <div
      role="status"
      aria-live="polite"
      className={`rounded-os border px-4 py-3 text-[13px] ${className}`}
      style={ok
        ? { borderColor: "rgba(31,170,89,.35)", background: "rgba(31,170,89,.06)", color: "var(--os-green)" }
        : { borderColor: "var(--os-red)", background: "rgba(230,0,39,.05)", color: "var(--os-red)" }}
    >
      {texte}
    </div>
  );
}

"use client";

// Primitives UI Osirion — réutilisées par les écrans (tokens os-*, coins nets).
import { RefreshCw } from "lucide-react";

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-[22px] font-bold text-os-t1 leading-tight">{title}</h1>
        {subtitle && <p className="text-[13px] text-os-t3 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
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
    <div className="inline-flex items-center gap-1 rounded-os border border-os-border bg-os-card p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            /* Onglet actif = BLEU de marque. Le libellé passe en SOMBRE
               (--os-on-primary) : du blanc sur ce bleu tomberait à 2,1:1. */
            className={`rounded-os ${pad} font-medium transition-colors ${
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

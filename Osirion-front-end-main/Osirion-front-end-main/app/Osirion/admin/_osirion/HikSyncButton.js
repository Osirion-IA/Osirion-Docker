"use client";

// Bouton de synchronisation MANUELLE du catalogue HikCentral. Autonome : vérifie
// d'abord /api/hikcentral/status et ne s'affiche QUE si le connecteur est
// configuré. Au clic → POST /api/hikcentral/sync, puis résumé transitoire
// (sites · caméras · nouvelles). Complète la synchro périodique automatique.
import { useState, useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

export default function HikSyncButton({ onSynced }) {
  const [configured, setConfigured] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { ok, text }

  useEffect(() => {
    (async () => {
      try {
        const r = await fetchWithRefresh("/api/hikcentral/status");
        if (r?.ok) { const d = await r.json(); setConfigured(!!d?.configured); }
      } catch { /* connecteur indisponible → bouton masqué */ }
    })();
  }, []);

  if (!configured) return null;

  const sync = async () => {
    setBusy(true); setResult(null);
    try {
      const r = await fetchWithRefresh("/api/hikcentral/sync", { method: "POST" });
      const d = await r.json().catch(() => ({}));
      if (r?.ok) {
        const news = d.created ?? 0;
        setResult({ ok: true, text: `${d.areas ?? 0} sites · ${d.cameras_total ?? 0} caméras${news ? ` · +${news} nouvelle(s)` : ""}` });
        onSynced?.();
      } else {
        setResult({ ok: false, text: d?.detail || d?.message || "Échec de la synchronisation." });
      }
    } catch {
      setResult({ ok: false, text: "Erreur réseau." });
    } finally {
      setBusy(false);
      setTimeout(() => setResult(null), 6000);
    }
  };

  return (
    <div className="inline-flex items-center gap-2.5">
      {result && (
        <span className={`text-[12px] ${result.ok ? "text-os-green" : "text-os-red"} max-w-[280px] truncate`} title={result.text}>
          {result.text}
        </span>
      )}
      <button
        onClick={sync}
        disabled={busy}
        title="Récupère les caméras et sites depuis HikCentral"
        className="h-9 px-3 inline-flex items-center gap-2 rounded-os border border-os-border bg-os-card text-[13px] text-os-t2 hover:text-os-t1 disabled:opacity-50"
      >
        <RefreshCw className={`h-4 w-4 ${busy ? "os-anim-spin" : ""}`} /> Synchroniser HikCentral
      </button>
    </div>
  );
}

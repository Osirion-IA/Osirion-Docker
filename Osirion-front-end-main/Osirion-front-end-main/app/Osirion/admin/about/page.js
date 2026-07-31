"use client";

/**
 * À propos — présentation brève de la plateforme (section Système, thème clair).
 */
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card } from "../_osirion/ui";

const VERSION = "2.0";

export default function AboutPage() {
  return (
    <OsShell>
      <div className="p-6 max-w-2xl">
        <PageHeader title="À propos" />

        <Card className="p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-[26px] font-bold text-os-t1 leading-tight">Qwiper Sentinel</h2>
            <span className="os-num shrink-0 rounded-os border border-os-border bg-os-card-2 px-3 py-1.5 text-[13px] text-os-t2">version {VERSION}</span>
          </div>

          <p className="text-[14px] text-os-t2 mt-4 leading-relaxed">
            Plateforme d'intelligence opérationnelle basée sur la vidéo : elle transforme vos
            caméras en capteurs de données (fréquentation, occupation, files d'attente, alertes).
          </p>

          <div className="mt-6 pt-5 border-t border-os-border grid grid-cols-2 gap-4 text-[13px]">
            <div>
              <p className="text-os-t4 text-[12px]">Version</p>
              <p className="os-num text-os-t1 font-semibold mt-0.5">{VERSION}</p>
            </div>
            <div>
              <p className="text-os-t4 text-[12px]">Éditeur</p>
              <p className="text-os-t1 font-semibold mt-0.5">Qwiper</p>
            </div>
          </div>
        </Card>

        <p className="text-[11px] text-os-t4 mt-6 text-center">© {new Date().getFullYear()} Qwiper Sentinel</p>
      </div>
    </OsShell>
  );
}

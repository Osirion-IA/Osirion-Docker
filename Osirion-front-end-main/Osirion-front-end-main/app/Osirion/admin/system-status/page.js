"use client";

/**
 * Système & accès — section Configurer (thème clair). Synthèse : KPIs système
 * (CPU/mémoire/stockage + conformité RGPD), utilisateurs & rôles, journal d'audit.
 * La gestion CRUD complète des comptes reste sur /Osirion/admin/users.
 * Données : /api/systemHealth, /api/users, /api/audit.
 */
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Cpu, MemoryStick, HardDrive } from "lucide-react";
import OsShell from "../_osirion/OsShell";
import { PageHeader, Card } from "../_osirion/ui";
import { useAuth } from "../AuthContext";
import { fetchWithRefresh } from "../../../lib/fetchWithRefresh";

const ROLE_META = {
  admin: { label: "Administrateur", color: "var(--os-red)" },
  user: { label: "Opérateur", color: "var(--os-blue)" },
  viewer: { label: "Observateur", color: "var(--os-t3)" },
};
const fmtBytes = (b) => {
  if (typeof b !== "number" || b <= 0) return "—";
  const u = ["o", "Ko", "Mo", "Go", "To"]; let s = b, i = 0;
  while (s >= 1024 && i < u.length - 1) { s /= 1024; i++; }
  return `${s.toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
};
function relTime(ts) {
  const d = new Date(ts && !String(ts).endsWith("Z") ? `${ts}Z` : ts);
  if (isNaN(d)) return "—";
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  if (m < 1440) return `il y a ${Math.floor(m / 60)} h`;
  return `il y a ${Math.floor(m / 1440)} j`;
}
const clock = (ts) => { const d = new Date(ts && !String(ts).endsWith("Z") ? `${ts}Z` : ts); return isNaN(d) ? "—" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); };
const auditColor = (a) => (/(alerte|acquitt)/i.test(a) ? "var(--os-red)" : /(connexion|login)/i.test(a) ? "var(--os-blue)" : /(gel|erreur|échou)/i.test(a) ? "var(--os-amber)" : "var(--os-t3)");

function Tile({ label, value, hint, icon: Icon, color }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-os-t3">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-os-t4" strokeWidth={1.8} />}
      </div>
      <p className="os-num mt-3 text-[26px] leading-none font-bold" style={{ color: color || "var(--os-t1)" }}>{value}</p>
      {hint && <p className="text-[12px] text-os-t3 mt-2">{hint}</p>}
    </Card>
  );
}

export default function SystemAccessPage() {
  const user = useAuth();
  const isAdmin = user?.role === "admin";
  const [sys, setSys] = useState(null);
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);

  const load = useCallback(async () => {
    const [s, u, a] = await Promise.all([
      fetch("/api/systemHealth").then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetchWithRefresh("/api/users").then((r) => (r?.ok ? r.json() : [])).catch(() => []),
      fetchWithRefresh("/api/audit").then((r) => (r?.ok ? r.json() : [])).catch(() => []),
    ]);
    setSys(s);
    setUsers(Array.isArray(u) ? u : []);
    setLogs(Array.isArray(a) ? a : (a?.logs || []));
  }, []);
  useEffect(() => { if (isAdmin) load(); }, [load, isAdmin]);

  if (user && !isAdmin) {
    return (
      <OsShell>
        <div className="p-6"><Card className="p-10 text-center"><p className="text-[14px] text-os-t2">Accès réservé aux administrateurs.</p></Card></div>
      </OsShell>
    );
  }

  const disk = sys?.disks?.[0];
  const cpuPct = Math.round(sys?.cpu?.total_usage_percent ?? sys?.cpu?.percent ?? 0);
  const ramPct = Math.round(sys?.ram?.percent ?? 0);
  const diskPct = Math.round(disk?.percent ?? 0);
  // `used`/`total` arrivent DÉJÀ formatés en chaînes ("15.2GB") ; les repasser
  // dans fmtBytes rendait « — / — ». Les octets bruts sont sous `raw_bytes`.
  const ramBytes = sys?.ram?.raw_bytes;
  const diskBytes = disk?.raw_bytes;

  return (
    <OsShell>
      <div className="p-6">
        <PageHeader title="Système & accès" subtitle="Utilisateurs, journal d'audit et état du système" />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
          <Tile label="Processeur" value={`${cpuPct} %`} hint="charge CPU" icon={Cpu} color={cpuPct >= 85 ? "var(--os-red)" : "var(--os-t1)"} />
          <Tile label="Mémoire" value={`${ramPct} %`} hint={ramBytes ? `${fmtBytes(ramBytes.used)} / ${fmtBytes(ramBytes.total)}` : "—"} icon={MemoryStick} color={ramPct >= 85 ? "var(--os-red)" : "var(--os-t1)"} />
          <Tile label="Stockage flux" value={disk ? `${diskPct} %` : "—"} hint={diskBytes ? `${fmtBytes(diskBytes.used)} / ${fmtBytes(diskBytes.total)}` : "—"} icon={HardDrive} color={diskPct >= 90 ? "var(--os-red)" : "var(--os-t1)"} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_0.7fr] gap-4">
          <Card className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[15px] font-semibold text-os-t1">Utilisateurs &amp; rôles</h3>
              <Link href="/Osirion/admin/users" className="px-3 py-1.5 rounded-os border border-os-border text-[12px] text-os-t2 hover:text-os-t1">Gérer</Link>
            </div>
            {users.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-4">Aucun utilisateur.</p>
            ) : (
              <ul>
                {users.map((u) => {
                  const rm = ROLE_META[u.role] || { label: u.role, color: "var(--os-t3)" };
                  return (
                    <li key={u.id} className="flex items-center gap-3 py-3 border-b border-os-border last:border-0">
                      <span className="h-9 w-9 rounded-os bg-os-card-2 border border-os-border-2 grid place-items-center os-num text-[12px] font-semibold text-os-t2">
                        {(u.fullName || u.email || "?").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join("")}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-semibold text-os-t1 truncate">{u.fullName || u.email}</p>
                        <p className="text-[12px] text-os-t3 truncate">{u.email}</p>
                      </div>
                      <span className="text-[12px] font-semibold shrink-0" style={{ color: rm.color }}>{rm.label}</span>
                      <span className="text-[11px] text-os-t4 shrink-0 w-24 text-right">{u.is_active ? relTime(u.last_login) || "—" : "inactif"}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <h3 className="text-[15px] font-semibold text-os-t1 mb-4">Journal d&apos;audit</h3>
            {logs.length === 0 ? (
              <p className="text-[13px] text-os-t3 py-4">Aucune entrée.</p>
            ) : (
              <ul className="space-y-3.5">
                {logs.slice(0, 8).map((l) => (
                  <li key={l.id} className="flex gap-3">
                    <span className="mt-1.5 h-2 w-2 rounded-full shrink-0" style={{ background: auditColor(l.action) }} />
                    <div className="min-w-0">
                      <p className="text-[13px] text-os-t1 leading-snug">{l.action}{l.detail ? ` — ${l.detail}` : ""}</p>
                      <p className="os-num text-[11px] text-os-t4 mt-0.5">{clock(l.created_at)} · {l.user_email || "Système"}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </OsShell>
  );
}

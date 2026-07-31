"use client";

// Sidebar Osirion — CHARBON dans les deux thèmes. ACCORDÉON : tous les écrans,
// groupés par section, chaque groupe repliable. La section active est ouverte par
// défaut (et s'ouvre à la navigation). Item actif = accent gauche rouge 3px.
import { useState, useEffect } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { activeScreenHref } from "./nav";

export default function OsSidebar({ sections, activeKey, activePath, alertsCount = 0 }) {
  const [open, setOpen] = useState(() => new Set([activeKey]));

  // À la navigation vers une autre section, on ouvre son groupe (sans fermer les autres).
  useEffect(() => {
    setOpen((prev) => (prev.has(activeKey) ? prev : new Set(prev).add(activeKey)));
  }, [activeKey]);

  const toggle = (k) =>
    setOpen((prev) => {
      const n = new Set(prev);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });

  return (
    <aside className="shrink-0 w-[230px] bg-os-sidebar border-r border-os-sidebar-border sticky top-[52px] h-[calc(100vh-52px)] flex flex-col overflow-y-auto">
      <nav className="px-3 py-3 flex-1 space-y-1">
        {sections.map((s) => {
          const isOpen = open.has(s.key);
          const isActiveSection = s.key === activeKey;
          const activeHref = isActiveSection ? activeScreenHref(s, activePath) : null;
          const sectionBadge = s.screens.some((sc) => sc.badge === "alerts") && alertsCount > 0;
          return (
            <div key={s.key}>
              <button
                onClick={() => toggle(s.key)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-os text-[12px] font-semibold uppercase tracking-[0.1em] transition-colors ${
                  isActiveSection ? "text-white" : "text-[#8a929b] hover:text-[#c3c8ce]"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${isActiveSection ? "bg-os-green" : "bg-[#4b535c]"}`} />
                <span className="flex-1 text-left">{s.label}</span>
                {sectionBadge && !isOpen && (
                  <span className="os-num min-w-[18px] h-[18px] px-1 grid place-items-center rounded-full bg-os-red text-white text-[10px] font-semibold leading-none">
                    {alertsCount > 99 ? "99+" : alertsCount}
                  </span>
                )}
                <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${isOpen ? "" : "-rotate-90"}`} strokeWidth={2} />
              </button>

              {isOpen && (
                <div className="mt-0.5 mb-1.5 space-y-0.5">
                  {s.screens.map((sc) => {
                    const active = sc.href === activeHref;
                    const Icon = sc.icon;
                    const showBadge = sc.badge === "alerts" && alertsCount > 0;
                    return (
                      <Link
                        key={sc.href}
                        href={sc.href}
                        className={`relative flex items-center gap-3 pl-6 pr-3 py-2 rounded-os text-[13px] transition-colors ${
                          active
                            ? "bg-white/[0.06] text-white font-medium"
                            : "text-[#8a929b] hover:text-[#c3c8ce] hover:bg-white/[0.03]"
                        }`}
                      >
                        {active && <span className="absolute left-1 top-1/2 -translate-y-1/2 h-6 w-[3px] rounded-r bg-os-red" />}
                        <Icon className="h-[17px] w-[17px] shrink-0" strokeWidth={1.9} />
                        <span className="truncate">{sc.label}</span>
                        {showBadge && (
                          <span className="os-num ml-auto min-w-[20px] h-5 px-1.5 grid place-items-center rounded-full bg-os-red text-white text-[11px] font-semibold leading-none">
                            {alertsCount > 99 ? "99+" : alertsCount}
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

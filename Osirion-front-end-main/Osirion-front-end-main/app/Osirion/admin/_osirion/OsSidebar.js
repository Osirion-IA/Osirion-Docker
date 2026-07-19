"use client";

// Sidebar Osirion — CHARBON dans les deux thèmes (couleurs de texte fixes, jamais
// les tokens --os-t* qui s'inversent). Item actif = accent gauche rouge 3px.
import Link from "next/link";
import { activeScreenHref } from "./nav";

export default function OsSidebar({ section, activePath, alertsCount = 0, camsOnline = 0, camsTotal = 0 }) {
  const activeHref = activeScreenHref(section, activePath);
  return (
    <aside className="shrink-0 w-[230px] bg-os-sidebar border-r border-os-sidebar-border sticky top-[52px] h-[calc(100vh-52px)] flex flex-col">
      <div className="px-5 pt-5 pb-4">
        <p className="text-[11px] font-semibold tracking-[0.14em] uppercase text-[#6b7480]">{section.kicker}</p>
        <div className="mt-1.5 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-os-green os-anim-pulse" />
          <h2 className="text-[17px] font-semibold text-white leading-tight">{section.title}</h2>
        </div>
      </div>

      <nav className="px-3 flex-1 space-y-0.5">
        {section.screens.map((sc) => {
          const active = sc.href === activeHref;
          const Icon = sc.icon;
          const showBadge = sc.badge === "alerts" && alertsCount > 0;
          return (
            <Link
              key={sc.href}
              href={sc.href}
              className={`relative flex items-center gap-3 pl-4 pr-3 py-2.5 rounded-os text-[13px] transition-colors ${
                active
                  ? "bg-white/[0.06] text-white font-medium"
                  : "text-[#8a929b] hover:text-[#c3c8ce] hover:bg-white/[0.03]"
              }`}
            >
              {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-[3px] rounded-r bg-os-red" />}
              <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.9} />
              <span className="truncate">{sc.label}</span>
              {showBadge && (
                <span className="os-num ml-auto min-w-[20px] h-5 px-1.5 grid place-items-center rounded-full bg-os-red text-white text-[11px] font-semibold leading-none">
                  {alertsCount > 99 ? "99+" : alertsCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* <div className="px-5 py-4 border-t border-os-sidebar-border">
        <p className="text-[12px] text-[#8a929b]">
          <span className="os-num text-[#c3c8ce] font-medium">{camsOnline}</span>
          <span className="text-[#6b7480]">/{camsTotal}</span> caméras en ligne
        </p>
      </div> */}
    </aside>
  );
}

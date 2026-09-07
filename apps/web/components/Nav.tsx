"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Arena" },
  { href: "/catalog", label: "Data catalog" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/learn", label: "Learn" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-ink-800/80 bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] items-center gap-3 px-4 py-3 sm:gap-6 sm:px-6">
        <Link href="/" className="group flex shrink-0 items-center gap-2.5">
          <span className="relative flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-arena-graph to-arena-ontology text-[13px] font-bold text-ink-950">
            R
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-ink-100">
            Retrieval Arena
          </span>
        </Link>

        {/* Four links no longer fit a 390px viewport at full padding, so the nav
            tightens up before it is allowed to push the page sideways. */}
        <nav className="scroll-slim ml-auto flex min-w-0 items-center gap-0.5 overflow-x-auto sm:gap-1">
          {LINKS.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`shrink-0 whitespace-nowrap rounded-md px-2 py-1.5 text-[13px] transition sm:px-3 ${
                  active
                    ? "bg-ink-800 text-ink-100"
                    : "text-ink-300 hover:bg-ink-850 hover:text-ink-100"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

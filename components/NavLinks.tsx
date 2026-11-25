"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Home", match: (p: string) => p === "/" },
  { href: "/possible", label: "POSSIBLE" },
  { href: "/noise", label: "NOISE" },
  { href: "/batch", label: "Batch" },
  { href: "/invariants", label: "Invariants" },
  { href: "/audit", label: "Audit" },
];

function isActive(pathname: string, href: string, match?: (p: string) => boolean): boolean {
  if (match) return match(pathname);
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="nav-pills" aria-label="Demo routes">
      {links.map((l) => (
        <Link key={l.href} href={l.href} data-active={isActive(pathname, l.href, l.match)}>
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Winnow — mock demo",
  description: "Binary POSSIBLE / NOISE outreach demo",
};

const links = [
  { href: "/", label: "Home" },
  { href: "/possible", label: "POSSIBLE" },
  { href: "/noise", label: "NOISE" },
  { href: "/batch", label: "Batch" },
  { href: "/invariants", label: "Invariants" },
  { href: "/audit", label: "Audit" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          {links.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
        </nav>
        {children}
      </body>
    </html>
  );
}
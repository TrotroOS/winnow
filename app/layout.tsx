import type { Metadata } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/NavLinks";
import "./globals.css";

export const metadata: Metadata = {
  title: "Winnow — mock demo",
  description: "Binary POSSIBLE / NOISE outreach demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="site-header">
            <div className="site-header__inner">
              <Link href="/" className="brand">
                <span className="brand__mark" aria-hidden />
                <span>Winnow</span>
                <span className="brand__tag">mock demo</span>
              </Link>
              <NavLinks />
            </div>
          </header>
          <div className="page-content">{children}</div>
          <footer className="site-footer muted">
            Inspection demo · binary POSSIBLE / NOISE only · no scores or ranks
          </footer>
        </div>
      </body>
    </html>
  );
}
import type { Metadata } from "next";

import { Nav } from "@/components/Nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "Retrieval Arena — see how machines find things",
  description:
    "A hands-on comparison of keyword, semantic, graph, hybrid and ontology-aware retrieval over the same basketball corpus. Every result shows the SQL or Cypher that produced it.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Nav />
        {children}
        <footer className="mx-auto max-w-[1400px] px-4 py-10 text-[11px] leading-relaxed text-ink-500 sm:px-6">
          <p>
            Retrieval Arena is a teaching sandbox. The corpus is hand-authored:
            player statistics are approximate public-record values for roughly the
            2023-24 season, and the articles are original neutral summaries of
            publicly reported events written for this demo — not reproductions of
            real articles, and containing no invented quotes. Six articles are
            deliberate retrieval traps.
          </p>
        </footer>
      </body>
    </html>
  );
}

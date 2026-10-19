"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Overview", href: "/" },
  { label: "Competitors", href: "/competitors" },
  { label: "Outliers", href: "/outliers" },
  { label: "Content Library", href: "/library" },
];

const BOTTOM_ITEMS = [{ label: "Settings", href: "/settings" }];

export function Sidebar() {
  const path = usePathname();

  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  return (
    <nav
      style={{
        width: 216,
        flexShrink: 0,
        background: "var(--surface)",
        borderRight: "1px solid var(--line)",
        padding: "20px 16px",
        display: "flex",
        flexDirection: "column",
        position: "sticky",
        top: 0,
        height: "100vh",
      }}
    >
      <div
        style={{
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: "0.02em",
          margin: "0 0 28px 2px",
        }}
      >
        CONTENT OUTLIER
      </div>

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        {NAV_ITEMS.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              style={{
                display: "block",
                width: "100%",
                padding: "8px 10px",
                fontSize: 13.5,
                color: isActive(item.href) ? "var(--ink)" : "var(--ink-soft)",
                fontWeight: isActive(item.href) ? 600 : 400,
                borderRadius: "var(--radius)",
                borderLeft: isActive(item.href)
                  ? "2px solid var(--accent)"
                  : "2px solid transparent",
                background: isActive(item.href) ? "var(--accent-bg)" : "transparent",
                transition: "color 0.12s, background 0.12s",
                textDecoration: "none",
              }}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>

      <div style={{ height: 1, background: "var(--line)", margin: "12px 2px" }} />

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        {BOTTOM_ITEMS.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              style={{
                display: "block",
                width: "100%",
                padding: "8px 10px",
                fontSize: 13.5,
                color: isActive(item.href) ? "var(--ink)" : "var(--ink-soft)",
                fontWeight: isActive(item.href) ? 600 : 400,
                borderRadius: "var(--radius)",
                borderLeft: isActive(item.href)
                  ? "2px solid var(--accent)"
                  : "2px solid transparent",
                background: isActive(item.href) ? "var(--accent-bg)" : "transparent",
                textDecoration: "none",
              }}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>

      <div
        style={{
          marginTop: "auto",
          fontSize: 11.5,
          color: "var(--ink-soft)",
          padding: 2,
        }}
      >
        v1.0 · MVP
      </div>
    </nav>
  );
}

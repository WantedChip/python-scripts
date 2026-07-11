import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Browse Scripts",
  description: "Browse the full catalog of Python scripts — coming soon.",
};

/**
 * Browse page — Phase 0 placeholder.
 * Styled consistently with the rest of the site; no default 404 look.
 * Full browse/search functionality arrives in Phase 1.
 */
export default function BrowsePage() {
  return (
    <div
      style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}
      className="min-h-full flex items-center justify-center py-24 px-6"
    >
      <div className="text-center max-w-lg">
        {/* Terminal animation */}
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "3rem",
            marginBottom: "1.5rem",
            lineHeight: 1,
          }}
          aria-hidden="true"
        >
          <span style={{ color: "var(--accent)" }}>$</span>
          <span
            style={{ color: "var(--text-muted)" }}
          >
            {" "}browse --all
          </span>
          <span
            style={{
              display: "inline-block",
              width: "2px",
              height: "2.5rem",
              backgroundColor: "var(--accent)",
              marginLeft: "4px",
              verticalAlign: "middle",
              animation: "blink 1.1s step-end infinite",
            }}
          />
        </div>

        {/* Cursor blink animation */}
        <style>{`
          @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0; }
          }
        `}</style>

        <h1
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "1.75rem",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            marginBottom: "1rem",
          }}
        >
          Browse is coming in Phase 1
        </h1>

        <p
          style={{
            color: "var(--text-muted)",
            fontSize: "1rem",
            lineHeight: 1.7,
            marginBottom: "2rem",
          }}
        >
          Full script browsing, search, category filtering, and one-click
          downloads are being built right now. In the meantime, explore the
          full index on GitHub.
        </p>

        {/* Status pill */}
        <div
          className="flex justify-center mb-6"
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.8125rem",
              color: "var(--warning)",
              border: "1px solid rgba(245,158,11,0.3)",
              backgroundColor: "rgba(245,158,11,0.08)",
              padding: "0.25rem 0.875rem",
              borderRadius: "99px",
              letterSpacing: "0.04em",
            }}
          >
            ⧖ In development — Phase 1
          </span>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <a
            href="https://github.com/WantedChip/python-scripts/blob/main/INDEX.md"
            target="_blank"
            rel="noopener noreferrer"
            id="browse-index-link"
            style={{
              backgroundColor: "var(--accent)",
              color: "#fff",
              fontFamily: "var(--font-mono)",
              fontWeight: 600,
              fontSize: "0.9375rem",
              padding: "0.6875rem 1.5rem",
              borderRadius: "0.5rem",
              transition: "background-color 0.15s ease",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.375rem",
            }}
            className="hover:bg-[var(--accent-dim)]"
          >
            View INDEX.md on GitHub
          </a>

          <Link
            href="/"
            id="browse-home-link"
            style={{
              backgroundColor: "var(--surface)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.9375rem",
              padding: "0.6875rem 1.5rem",
              borderRadius: "0.5rem",
              transition: "background-color 0.15s ease",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.375rem",
            }}
            className="hover:bg-[var(--surface-hover)]"
          >
            ← Back home
          </Link>
        </div>
      </div>
    </div>
  );
}

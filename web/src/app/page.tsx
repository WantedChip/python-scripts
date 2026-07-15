import Link from "next/link";
import type { Metadata } from "next";
import { existsSync } from "fs";
import { readFileSync } from "fs";
import { join } from "path";
import { Script } from "@/lib/search/types";
import StatsStrip from "@/components/StatsStrip";

export const metadata: Metadata = {
  title: "PyScripts — Python CLI Scripts Library",
  description:
    "A curated library of high-quality, fully-tested Python CLI scripts for automation, system tools, data processing, and more.",
};

/** Load scripts.json from the data directory. Returns [] if not found. */
function loadScripts(): Script[] {
  try {
    const dataPath = join(process.cwd(), "src", "data", "scripts.json");
    if (!existsSync(dataPath)) return [];
    const raw = readFileSync(dataPath, "utf8");
    return JSON.parse(raw) as Script[];
  } catch {
    return [];
  }
}

/** Derive unique categories from the script list. */
function getCategories(scripts: Script[]): string[] {
  return [...new Set(scripts.map((s) => s.category))];
}

export default function HomePage() {
  const scripts = loadScripts();
  const categories = getCategories(scripts);
  const totalScripts = scripts.length;
  const totalCategories = categories.length;

  // Group by category for the preview grid
  const categorySummary = categories.map((cat) => ({
    name: cat,
    count: scripts.filter((s) => s.category === cat).length,
    sample: scripts.filter((s) => s.category === cat).slice(0, 3),
  }));

  return (
    <div
      style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}
      className="min-h-full"
    >
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* Subtle grid background */}
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "radial-gradient(circle at 60% 0%, rgba(124,58,237,0.12) 0%, transparent 60%)",
            pointerEvents: "none",
          }}
        />

        <div className="relative max-w-6xl mx-auto px-6 pt-24 pb-20">
          {/* Terminal badge */}
          <div className="flex justify-center mb-8">
            <span
              style={{
                fontFamily: "var(--font-mono)",
                color: "var(--accent)",
                fontSize: "0.8125rem",
                border: "1px solid var(--accent-glow)",
                backgroundColor: "var(--accent-subtle)",
                padding: "0.25rem 0.875rem",
                borderRadius: "99px",
                letterSpacing: "0.05em",
              }}
            >
              $ open-source · python · cli
            </span>
          </div>

          {/* Main heading */}
          <h1
            className="text-center"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "clamp(2.5rem, 6vw, 4.5rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              lineHeight: 1.1,
              marginBottom: "1.5rem",
            }}
          >
            A library of{" "}
            <span style={{ color: "var(--accent)" }}>production-quality</span>
            <br />
            Python scripts.
          </h1>

          {/* Tagline */}
          <p
            className="text-center max-w-xl mx-auto"
            style={{
              color: "var(--text-muted)",
              fontSize: "1.125rem",
              lineHeight: 1.7,
              marginBottom: "2.5rem",
            }}
          >
            Every script is type-checked, linted, tested, and ready to run.
            No framework. No bloat. Just Python that works.
          </p>

          {/* CTA buttons */}
          <div className="flex flex-wrap items-center justify-center gap-3 mb-16">
            <Link
              href="/browse"
              id="hero-browse-button"
              style={{
                backgroundColor: "var(--accent)",
                color: "#fff",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                fontSize: "0.9375rem",
                padding: "0.75rem 1.75rem",
                borderRadius: "0.5rem",
                transition: "background-color 0.15s ease, transform 0.1s ease",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
              className="hover:bg-[var(--accent-dim)] active:scale-[0.98]"
            >
              Browse all scripts
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>

            <a
              href="https://github.com/WantedChip/python-scripts"
              target="_blank"
              rel="noopener noreferrer"
              id="hero-github-button"
              style={{
                backgroundColor: "var(--surface)",
                color: "var(--text)",
                border: "1px solid var(--border)",
                fontFamily: "var(--font-mono)",
                fontWeight: 500,
                fontSize: "0.9375rem",
                padding: "0.75rem 1.75rem",
                borderRadius: "0.5rem",
                transition: "background-color 0.15s ease",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
              className="hover:bg-[var(--surface-hover)]"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M12 0C5.373 0 0 5.373 0 12c0 5.303 3.438 9.8 8.205 11.387.6.113.82-.26.82-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.757-1.333-1.757-1.089-.744.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.51 11.51 0 0112 5.803a11.51 11.51 0 013.002.404c2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.218.694.825.576C20.565 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
              View on GitHub
            </a>
          </div>

          {/* ── Live Stats Strip ─────────────────────────────────────────── */}
          {totalScripts > 0 && (
            <div
              style={{
                borderTop: "1px solid var(--border)",
                paddingTop: "2rem",
              }}
            >
              <StatsStrip />
            </div>
          )}
        </div>
      </section>

      {/* ── Category Grid ─────────────────────────────────────────────────── */}
      {categorySummary.length > 0 && (
        <section
          style={{ borderTop: "1px solid var(--border)" }}
          className="py-20"
        >
          <div className="max-w-6xl mx-auto px-6">
            <h2
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "1.25rem",
                fontWeight: 600,
                letterSpacing: "-0.01em",
                marginBottom: "0.5rem",
              }}
            >
              Browse by category
            </h2>
            <p
              style={{
                color: "var(--text-muted)",
                fontSize: "0.9375rem",
                marginBottom: "2rem",
              }}
            >
              {totalCategories} categories, {totalScripts} scripts total.
            </p>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {categorySummary.map((cat) => (
                <CategoryCard key={cat.name} category={cat} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Quality bar ───────────────────────────────────────────────────── */}
      <section
        style={{ borderTop: "1px solid var(--border)" }}
        className="py-16"
      >
        <div className="max-w-6xl mx-auto px-6">
          <h2
            className="text-center"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "1.25rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
              marginBottom: "2rem",
            }}
          >
            Every script clears the same quality gate
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <QualityItem
              icon="✓"
              title="pylint 10/10"
              desc="Perfect static analysis score"
            />
            <QualityItem
              icon="✓"
              title="mypy strict"
              desc="Full type-hint coverage"
            />
            <QualityItem
              icon="✓"
              title="≥80% coverage"
              desc="Tested logic, not just lines"
            />
            <QualityItem
              icon="✓"
              title="bandit clean"
              desc="No unresolved security findings"
            />
          </div>
        </div>
      </section>
    </div>
  );
}

/* ─── Sub-components ────────────────────────────────────────────────────────── */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function StatCard({ value, label }: { value: number; label: string }) {
  return (
    <div className="text-center">
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
          fontWeight: 700,
          color: "var(--accent)",
          lineHeight: 1,
          marginBottom: "0.375rem",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          color: "var(--text-muted)",
          fontSize: "0.875rem",
          textTransform: "lowercase",
          letterSpacing: "0.02em",
        }}
      >
        {label}
      </div>
    </div>
  );
}

interface CategorySummary {
  name: string;
  count: number;
  sample: Array<{ name: string; description: string }>;
}

function CategoryCard({ category }: { category: CategorySummary }) {
  return (
    <Link
      href="/browse"
      style={{
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "0.75rem",
        padding: "1.25rem",
        display: "block",
        transition: "border-color 0.15s ease, background-color 0.15s ease",
      }}
      className="hover:border-[var(--accent)] hover:bg-[var(--surface-raised)] group"
    >
      {/* Category header */}
      <div className="flex items-center justify-between mb-3">
        <span
          style={{
            fontFamily: "var(--font-mono)",
            color: "var(--accent)",
            fontSize: "0.8125rem",
            fontWeight: 600,
            letterSpacing: "0.04em",
          }}
        >
          {category.name}
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            color: "var(--text-dim)",
            fontSize: "0.75rem",
          }}
        >
          {category.count} script{category.count !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Sample scripts */}
      <ul className="space-y-1.5">
        {category.sample.map((script) => (
          <li
            key={script.name}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.8125rem",
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            className="group-hover:text-[var(--text)]"
            title={script.description}
          >
            <span style={{ color: "var(--text-dim)" }}>→ </span>
            {script.name}
          </li>
        ))}
      </ul>
    </Link>
  );
}

function QualityItem({
  icon,
  title,
  desc,
}: {
  icon: string;
  title: string;
  desc: string;
}) {
  return (
    <div
      style={{
        backgroundColor: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "0.75rem",
        padding: "1.25rem",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          color: "var(--success)",
          fontSize: "1.25rem",
          marginBottom: "0.5rem",
        }}
        aria-hidden="true"
      >
        {icon}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontWeight: 600,
          fontSize: "0.9375rem",
          marginBottom: "0.25rem",
        }}
      >
        {title}
      </div>
      <div
        style={{
          color: "var(--text-muted)",
          fontSize: "0.875rem",
        }}
      >
        {desc}
      </div>
    </div>
  );
}

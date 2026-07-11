import type { Metadata } from "next";
import Link from "next/link";
import { Folder, ArrowRight, ShieldCheck, Cpu, Code2 } from "lucide-react";
import scriptsData from "@/data/scripts.json";

export const metadata: Metadata = {
  title: "Browse Categories",
  description: "Browse PyScripts collection of utilities segmented by functional category.",
};

interface ScriptItem {
  category: string;
}

const CATEGORY_META: Record<string, { desc: string; icon: React.ReactNode; color: string }> = {
  automation: {
    desc: "Active monitors, automated file organization daemons, incremental backups, and webhook notifications.",
    icon: <Cpu className="h-6 w-6" />,
    color: "text-[var(--accent)] border-[var(--accent)]/20 bg-[var(--accent-subtle)]",
  },
  checkers: {
    desc: "Read-only syntax validators, environment audits, cron timeline health checkers, and SSL/WHOIS expiration alerts.",
    icon: <ShieldCheck className="h-6 w-6" />,
    color: "text-[var(--success)] border-[var(--success)]/20 bg-green-950/20",
  },
  tools: {
    desc: "CLI text utilities, Git repo cleanups, SQLite visual inspectors, subtitle correction engines, and screenshot OCR classification.",
    icon: <Code2 className="h-6 w-6" />,
    color: "text-[var(--warning)] border-[var(--warning)]/20 bg-amber-950/20",
  },
};

export default function BrowsePage() {
  const scripts = scriptsData as ScriptItem[];
  const categories = Array.from(new Set(scripts.map((s) => s.category)));

  // Calculate counts
  const categoryCounts = categories.reduce((acc, cat) => {
    acc[cat] = scripts.filter((s) => s.category === cat).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-5xl mx-auto flex flex-col gap-12">
        {/* Terminal Header */}
        <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-8">
          <div className="flex items-center gap-2 font-mono text-xs text-[var(--accent)]">
            <span>$</span>
            <span>pyscripts --list-categories</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--text)]">Browse Categories</h1>
          <p className="text-sm text-[var(--text-muted)] max-w-2xl leading-relaxed">
            Explore our curated repository of 28 high-quality Python utilities. Each script is fully standalone, typed, tested, and contains zero external supply-chain dependencies unless explicitly documented.
          </p>
        </div>

        {/* Categories Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {categories.map((cat) => {
            const meta = CATEGORY_META[cat] || {
              desc: `All ${cat} tools and scripts.`,
              icon: <Folder className="h-6 w-6" />,
              color: "text-[var(--text-muted)] border-[var(--border)] bg-[var(--surface-raised)]",
            };
            const count = categoryCounts[cat] || 0;

            return (
              <Link
                key={cat}
                href={`/browse/${cat}`}
                className="group flex flex-col justify-between p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-hover)] hover:border-[var(--text-dim)] transition-all cursor-pointer shadow-lg"
              >
                <div className="flex flex-col gap-4">
                  {/* Category icon */}
                  <div className={`h-12 w-12 rounded-lg border flex items-center justify-center ${meta.color}`}>
                    {meta.icon}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    {/* Category Title */}
                    <div className="flex items-center justify-between">
                      <h2 className="text-lg font-bold text-[var(--text)] capitalize tracking-tight">
                        {cat}
                      </h2>
                      <span className="font-mono text-[10px] text-[var(--text-dim)] bg-[var(--surface-raised)] border border-[var(--border)] px-2 py-0.5 rounded-full">
                        {count} {count === 1 ? "script" : "scripts"}
                      </span>
                    </div>
                    {/* Category Description */}
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                      {meta.desc}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-6 font-mono text-[11px] text-[var(--text-dim)] group-hover:text-[var(--text)] transition-colors">
                  <span>Explore category</span>
                  <ArrowRight className="h-3 w-3 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

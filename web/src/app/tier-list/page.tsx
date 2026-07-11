"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { Terminal, ArrowRight, Layers, HelpCircle } from "lucide-react";
import scriptsData from "@/data/scripts.json";
import { Script } from "@/lib/search/types";
import { calculateTier, getTierStyle, Tier } from "@/lib/tier";
import TierBadge from "@/components/TierBadge";

// Ordered list of tiers for rendering sequence
const TIER_ORDER: Tier[] = ["S", "A", "B", "C", "D", "Unranked"];

const TIER_DESCRIPTIONS: Record<Tier, { title: string; desc: string }> = {
  S: {
    title: "S-Tier: Gold Standard",
    desc: "Exceptional quality. Coverage >= 95% with 0 external dependencies (pure stdlib).",
  },
  A: {
    title: "A-Tier: Highly Reliable",
    desc: "Great quality. Coverage >= 90% with minimal (1-2) external dependencies.",
  },
  B: {
    title: "B-Tier: Standard Utilities",
    desc: "Good coverage (80-89%) or pure standard library tools with decent verification.",
  },
  C: {
    title: "C-Tier: Verifiable",
    desc: "Working tools with lower coverage (<80%) or higher external dependency footprints.",
  },
  D: {
    title: "D-Tier: Basic Implementations",
    desc: "Unverified tools or legacy scripts needing quality sweeps and tests.",
  },
  Unranked: {
    title: "Unranked: Awaiting Verification",
    desc: "Scripts that haven't defined standardized quality readouts inside their README.",
  },
};

export default function TierListPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const scripts = scriptsData as Script[];

  // Get unique categories for filtering pills
  const categories = useMemo(() => {
    return ["all", ...new Set(scripts.map((s) => s.category))];
  }, [scripts]);

  // Compute calculated tiers for scripts and group them
  const groupedScripts = useMemo(() => {
    const groups: Record<Tier, Script[]> = {
      S: [],
      A: [],
      B: [],
      C: [],
      D: [],
      Unranked: [],
    };

    scripts.forEach((script) => {
      // Filter by category first
      if (selectedCategory !== "all" && script.category !== selectedCategory) {
        return;
      }
      const tier = calculateTier(script.coveragePct, script.depCount, script.unranked);
      groups[tier].push(script);
    });

    // Sort scripts alphabetically within each group
    TIER_ORDER.forEach((tier) => {
      groups[tier].sort((a, b) => a.name.localeCompare(b.name));
    });

    return groups;
  }, [scripts, selectedCategory]);

  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-4xl mx-auto flex flex-col gap-10">
        {/* Terminal Header */}
        <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-8">
          <div className="flex items-center gap-2 font-mono text-xs text-[var(--text-dim)]">
            <Terminal className="h-4 w-4 text-[var(--accent)]" />
            <span>~/pyscripts/tier-list</span>
          </div>
          <h1 className="text-3xl font-mono font-bold tracking-tight text-[var(--text)]">
            Quality Leaderboard
          </h1>
          <p className="text-sm text-[var(--text-muted)] max-w-2xl leading-relaxed">
            Every script rated from S-tier to D-tier based on verifiable repository signals: 
            pylint ratings, unit test coverage percentages, and external dependency counts.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-mono text-[var(--text-dim)] mr-2">Filter category:</span>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded font-mono text-xs uppercase cursor-pointer border transition-colors ${
                selectedCategory === cat
                  ? "bg-[var(--accent-subtle)] text-[var(--accent)] border-[var(--accent)] font-semibold"
                  : "bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:text-[var(--text)]"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Tier Lists Sequence */}
        <div className="flex flex-col gap-12">
          {TIER_ORDER.map((tier) => {
            const list = groupedScripts[tier];
            if (list.length === 0 && selectedCategory !== "all") {
              // Hide empty sections when filtering to keep it dense
              return null;
            }

            const style = getTierStyle(tier);
            const desc = TIER_DESCRIPTIONS[tier];

            return (
              <section key={tier} className="flex flex-col gap-4">
                {/* Section Header */}
                <div
                  style={{ borderColor: style.borderColor }}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3"
                >
                  <div className="flex items-center gap-3">
                    <span
                      style={{
                        backgroundColor: style.backgroundColor,
                        borderColor: style.borderColor,
                        color: style.color,
                      }}
                      className="px-2.5 py-1 text-xs font-mono font-bold border rounded"
                    >
                      {tier === "Unranked" ? "UNRANKED" : `${tier}-TIER`}
                    </span>
                    <h2 className="text-sm font-mono font-semibold text-[var(--text)]">
                      {desc.title}
                    </h2>
                  </div>
                  <span className="text-xs font-mono text-[var(--text-dim)]">
                    {list.length} {list.length === 1 ? "script" : "scripts"}
                  </span>
                </div>
                
                <p className="text-xs text-[var(--text-muted)] leading-relaxed italic -mt-2">
                  {desc.desc}
                </p>

                {/* Scripts rows */}
                {list.length > 0 ? (
                  <div className="flex flex-col border border-[var(--border)] bg-[var(--surface)] rounded-xl overflow-hidden shadow-md divide-y divide-[var(--border)]">
                    {list.map((script) => (
                      <div
                        key={script.name}
                        className="flex flex-col sm:flex-row sm:items-center justify-between p-4 gap-4 hover:bg-[var(--surface-hover)] transition-colors group"
                      >
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2.5">
                            <Link
                              href={`/scripts/${script.category}/${script.name}`}
                              className="font-mono text-sm font-bold text-[var(--accent)] group-hover:underline"
                            >
                              {script.name}
                            </Link>
                            <span className="text-[9px] uppercase font-mono border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-1.5 py-0.2 rounded text-[var(--text-dim)]">
                              {script.category}
                            </span>
                          </div>
                          <p className="text-xs text-[var(--text-muted)] line-clamp-1 max-w-xl">
                            {script.description}
                          </p>
                        </div>

                        {/* Readouts & Actions */}
                        <div className="flex items-center justify-between sm:justify-end gap-6">
                          {/* Metrics reads */}
                          {!script.unranked ? (
                            <div className="flex items-center gap-3 font-mono text-[10px] text-[var(--text-dim)]">
                              <span>pylint: {script.pylintScore?.toFixed(2)}</span>
                              <span className="text-[var(--border)]">•</span>
                              <span>coverage: {script.coveragePct}%</span>
                              <span className="text-[var(--border)]">•</span>
                              <span>deps: {script.depCount}</span>
                            </div>
                          ) : (
                            <span className="font-mono text-[10px] text-[var(--text-dim)] italic">
                              metrics unavailable
                            </span>
                          )}

                          <Link
                            href={`/scripts/${script.category}/${script.name}`}
                            className="flex items-center gap-1.5 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                          >
                            <span>Inspect</span>
                            <ArrowRight className="h-3.5 w-3.5" />
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 rounded-xl border border-dashed border-[var(--border)] text-center text-xs text-[var(--text-dim)] font-mono">
                    No scripts currently ranked in this tier.
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

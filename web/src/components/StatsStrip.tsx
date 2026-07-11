import React, { useMemo } from "react";
import scriptsData from "@/data/scripts.json";
import { Script } from "@/lib/search/types";
import { calculateTier } from "@/lib/tier";

export default function StatsStrip() {
  const scripts = scriptsData as Script[];

  const stats = useMemo(() => {
    const total = scripts.length;
    const rankedScripts = scripts.filter((s) => !s.unranked);
    
    // Average coverage calculation
    const avgCoverage =
      rankedScripts.length > 0
        ? rankedScripts.reduce((acc, curr) => acc + (curr.coveragePct || 0), 0) /
          rankedScripts.length
        : 0;

    // Dependency free percent calculation
    const depFreeCount = scripts.filter((s) => s.depCount === 0).length;
    const depFreePct = total > 0 ? (depFreeCount / total) * 100 : 0;

    // Tier distribution compilation
    const tiers = { S: 0, A: 0, B: 0, C: 0, D: 0, Unranked: 0 };
    scripts.forEach((s) => {
      const tier = calculateTier(s.coveragePct, s.depCount, s.unranked);
      tiers[tier]++;
    });

    return {
      total,
      avgCoverage,
      depFreePct,
      tiers,
    };
  }, [scripts]);

  return (
    <div
      style={{
        borderColor: "var(--border)",
        backgroundColor: "var(--surface-raised)",
        color: "var(--text-muted)",
      }}
      className="border rounded-lg p-3 sm:p-4 font-mono text-[11px] sm:text-xs flex flex-col md:flex-row md:items-center justify-between gap-3 shadow"
    >
      {/* Title */}
      <div className="flex items-center gap-2">
        <span className="text-[var(--accent)] font-bold">●</span>
        <span className="text-[var(--text)] font-semibold uppercase tracking-wider">
          System Quality Metrics
        </span>
      </div>

      {/* Metrics Row */}
      <div className="flex flex-wrap items-center gap-y-2 gap-x-4 md:gap-x-6">
        <div>
          <span className="text-[var(--text-dim)]">TOTAL SCRIPTS:</span>{" "}
          <span className="text-[var(--text)] font-bold">{stats.total}</span>
        </div>
        
        <span className="hidden sm:inline text-[var(--border)]">|</span>
        
        <div>
          <span className="text-[var(--text-dim)]">AVG COVERAGE:</span>{" "}
          <span className="text-[var(--text)] font-bold">
            {stats.avgCoverage > 0 ? `${stats.avgCoverage.toFixed(1)}%` : "N/A"}
          </span>
        </div>

        <span className="hidden sm:inline text-[var(--border)]">|</span>

        <div>
          <span className="text-[var(--text-dim)]">DEP-FREE:</span>{" "}
          <span className="text-[var(--text)] font-bold">
            {stats.depFreePct.toFixed(1)}%
          </span>
        </div>

        <span className="hidden sm:inline text-[var(--border)]">|</span>

        <div className="flex items-center gap-1.5">
          <span className="text-[var(--text-dim)] mr-0.5">DISTRIBUTION:</span>
          <span className="text-[var(--accent)] font-bold">S:{stats.tiers.S}</span>
          <span className="text-[var(--text-dim)]">•</span>
          <span className="text-[var(--text)] font-semibold">A:{stats.tiers.A}</span>
          <span className="text-[var(--text-dim)]">•</span>
          <span className="text-[var(--text-muted)]">B:{stats.tiers.B}</span>
          {stats.tiers.C > 0 && (
            <>
              <span className="text-[var(--text-dim)]">•</span>
              <span className="text-[var(--text-dim)]">C:{stats.tiers.C}</span>
            </>
          )}
          {stats.tiers.D > 0 && (
            <>
              <span className="text-[var(--text-dim)]">•</span>
              <span className="text-[var(--text-dim)]">D:{stats.tiers.D}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

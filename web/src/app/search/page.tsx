"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { Search, Info, HelpCircle } from "lucide-react";
import scriptsData from "@/data/scripts.json";
import { searchScripts } from "@/lib/search";
import { matchBroad } from "@/lib/search/modes/broad";
import { matchStrict } from "@/lib/search/modes/strict";
import { matchWholeWord } from "@/lib/search/modes/wholeWord";
import { matchSubstring } from "@/lib/search/modes/substring";
import { matchFuzzy } from "@/lib/search/modes/fuzzy";
import { MatchSpan, SearchMode, Script } from "@/lib/search/types";
import TierBadge from "@/components/TierBadge";

// Mode description and example data to run through the engines
const MODE_DETAILS: Record<
  SearchMode,
  {
    title: string;
    desc: string;
    exampleQuery: string;
    exampleText: string;
  }
> = {
  Broad: {
    title: "Broad Match",
    desc: "Requires all query terms to exist anywhere in the text in any order, ranking by term proximity.",
    exampleQuery: "red apple",
    exampleText: "An apple that is bright red is tasty, unlike a green apple.",
  },
  Strict: {
    title: "Strict Match",
    desc: "Finds the exact normalized query string (collapses multiple spaces and matches case-insensitively).",
    exampleQuery: "env file",
    exampleText: "Create a custom env  file inside the project root.",
  },
  "Whole Word": {
    title: "Whole Word Match",
    desc: "Matches the query only where it stands as a separate, boundary-isolated word.",
    exampleQuery: "cat",
    exampleText: "The cat sat on a large category of mats.",
  },
  Substring: {
    title: "Substring Match",
    desc: "Simple case-insensitive search matching occurrences inside other words.",
    exampleQuery: "cat",
    exampleText: "The cat sat on a large category of mats.",
  },
  Fuzzy: {
    title: "Fuzzy Match",
    desc: "Typo-tolerant approximate matching (requires query length >= 3).",
    exampleQuery: "javascrit",
    exampleText: "Learning javascript is fun for developers.",
  },
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [activeMode, setActiveMode] = useState<SearchMode>("Broad");
  const [ignoreSeparators, setIgnoreSeparators] = useState(false);
  const [hoveredMode, setHoveredMode] = useState<SearchMode | null>(null);

  const scripts = scriptsData as Script[];

  // 1. Highlight Text Generator based on MatchSpans
  const renderHighlightedText = (text: string, matches: MatchSpan[]) => {
    if (matches.length === 0) return <span>{text}</span>;

    const elements: React.ReactNode[] = [];
    let lastIndex = 0;

    matches.forEach((span, idx) => {
      // Normal prefix
      if (span.start > lastIndex) {
        elements.push(<span key={`txt-${idx}`}>{text.substring(lastIndex, span.start)}</span>);
      }
      // Highlighted match
      elements.push(
        <mark
          key={`hl-${idx}`}
          className="bg-[var(--accent-glow)] text-[var(--text)] border-b border-[var(--accent)] font-semibold rounded px-0.5"
        >
          {text.substring(span.start, span.end)}
        </mark>
      );
      lastIndex = span.end;
    });

    // Normal suffix
    if (lastIndex < text.length) {
      elements.push(<span key="txt-end">{text.substring(lastIndex)}</span>);
    }

    return <>{elements}</>;
  };

  // 2. Perform live search
  const results = useMemo(() => {
    if (!query.trim()) return [];
    return searchScripts(query, scripts, activeMode, {
      ignoreSeparators,
    });
  }, [query, activeMode, ignoreSeparators, scripts]);

  // 3. Dynamic Tooltip Highlight Parser
  const renderTooltipExample = (mode: SearchMode) => {
    const detail = MODE_DETAILS[mode];
    let matchRes;

    // Run the actual core mode match function on the example data
    switch (mode) {
      case "Broad":
        matchRes = matchBroad(detail.exampleQuery, detail.exampleText);
        break;
      case "Strict":
        matchRes = matchStrict(detail.exampleQuery, detail.exampleText);
        break;
      case "Whole Word":
        matchRes = matchWholeWord(detail.exampleQuery, detail.exampleText);
        break;
      case "Substring":
        matchRes = matchSubstring(detail.exampleQuery, detail.exampleText);
        break;
      case "Fuzzy":
        matchRes = matchFuzzy(detail.exampleQuery, detail.exampleText);
        break;
    }

    return (
      <div className="flex flex-col gap-1.5 mt-2 pt-2 border-t border-[var(--border)] font-sans">
        <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-dim)]">
          <span>Query:</span>
          <code className="text-[var(--accent)] bg-[var(--surface)] px-1 rounded">
            &quot;{detail.exampleQuery}&quot;
          </code>
        </div>
        <div className="text-[10px] leading-relaxed text-[var(--text-muted)]">
          {renderHighlightedText(detail.exampleText, matchRes.matches)}
        </div>
      </div>
    );
  };

  const isFuzzyTooShort = activeMode === "Fuzzy" && query.trim().length > 0 && query.trim().length < 3;

  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-4xl mx-auto flex flex-col gap-10">
        {/* Header */}
        <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-8">
          <div className="flex items-center gap-2 font-mono text-xs text-[var(--accent)]">
            <span>$</span>
            <span>pyscripts --engine-search</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--text)]">Advanced Search</h1>
          <p className="text-sm text-[var(--text-muted)] max-w-2xl leading-relaxed">
            Search across our entire codebase, script descriptions, and README parameters using five granular search algorithms.
          </p>
        </div>

        {/* Controls Console */}
        <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] flex flex-col gap-6 shadow-md">
          {/* Query Search Bar */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search by keywords, file names, or features..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-[var(--surface-raised)] border border-[var(--border)] rounded-lg pl-11 pr-4 py-3 text-sm text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)] transition-all font-mono"
            />
            <Search className="absolute left-4 top-3.5 h-4.5 w-4.5 text-[var(--text-dim)]" />
          </div>

          {/* Mode Selector Row */}
          <div className="flex flex-col gap-2.5">
            <label className="text-xs font-semibold text-[var(--text-muted)] font-mono">
              Matching Algorithm
            </label>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(MODE_DETAILS) as SearchMode[]).map((mode) => {
                const isActive = activeMode === mode;
                return (
                  <div
                    key={mode}
                    className="relative"
                    onMouseEnter={() => setHoveredMode(mode)}
                    onMouseLeave={() => setHoveredMode(null)}
                  >
                    <button
                      onClick={() => setActiveMode(mode)}
                      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-mono font-medium border transition-all cursor-pointer ${
                        isActive
                          ? "bg-[var(--accent)] text-white border-transparent"
                          : "bg-[var(--surface-raised)] text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--surface-hover)]"
                      }`}
                    >
                      <span>{mode}</span>
                      <Info className="h-3.5 w-3.5 shrink-0 opacity-60 hover:opacity-100" />
                    </button>

                    {/* Rich Tooltip (derived dynamically) */}
                    {hoveredMode === mode && (
                      <div className="absolute left-0 bottom-full mb-2.5 z-30 w-64 bg-[var(--surface-raised)] border border-[var(--border)] p-3 rounded-lg shadow-xl text-left pointer-events-none">
                        <h4 className="text-xs font-bold text-[var(--text)] font-mono">
                          {MODE_DETAILS[mode].title}
                        </h4>
                        <p className="text-[10px] text-[var(--text-muted)] leading-relaxed mt-1">
                          {MODE_DETAILS[mode].desc}
                        </p>
                        {renderTooltipExample(mode)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Separators Checkbox */}
          <div className="flex items-center gap-2 border-t border-[var(--border-subtle)] pt-4">
            <input
              type="checkbox"
              id="ignore-separators"
              checked={ignoreSeparators}
              onChange={(e) => setIgnoreSeparators(e.target.checked)}
              className="accent-[var(--accent)] h-4 w-4 rounded cursor-pointer"
            />
            <label
              htmlFor="ignore-separators"
              className="text-xs text-[var(--text-muted)] cursor-pointer select-none font-mono"
            >
              Ignore Separators (strips <code className="bg-[var(--surface-raised)] border border-[var(--border)] px-1 rounded">- _ . , / \</code> during matching)
            </label>
          </div>
        </div>

        {/* Results */}
        <div className="flex flex-col gap-4">
          <h2 className="text-xs font-bold font-mono text-[var(--text-dim)] uppercase tracking-wider">
            Results {query.trim() && !isFuzzyTooShort && `(${results.length})`}
          </h2>

          {isFuzzyTooShort ? (
            <div className="text-center py-12 rounded-xl border border-[var(--warning)]/20 bg-amber-950/10 text-xs text-[var(--warning)] flex flex-col gap-2 items-center">
              <HelpCircle className="h-6 w-6" />
              <span>Fuzzy mode requires a query of at least 3 characters to scan properly.</span>
            </div>
          ) : query.trim() === "" ? (
            <div className="text-center py-16 rounded-xl border border-[var(--border)] bg-[var(--surface)] text-xs text-[var(--text-dim)]">
              Enter a search query in the console above to discover CLI scripts.
            </div>
          ) : results.length > 0 ? (
            <div className="flex flex-col gap-4">
              {results.map(({ script, nameMatches, descriptionMatches }) => (
                <div
                  key={script.name}
                  className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] flex flex-col sm:flex-row justify-between sm:items-center gap-4 hover:border-[var(--text-dim)] transition-all shadow-md group"
                >
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2.5">
                      {/* Name with highlights */}
                      <Link
                        href={`/scripts/${script.category}/${script.name}`}
                        className="font-mono text-sm font-bold text-[var(--accent)] group-hover:underline"
                      >
                        {renderHighlightedText(script.name, nameMatches)}
                      </Link>

                       <TierBadge
                        unranked={script.unranked}
                        coveragePct={script.coveragePct}
                        depCount={script.depCount}
                      />

                      <span className="text-[10px] capitalize font-mono border border-[var(--border)] bg-[var(--surface-raised)] px-2 py-0.5 rounded-full text-[var(--text-dim)]">
                        {script.category}
                      </span>
                    </div>

                    {/* Description with highlights */}
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed max-w-2xl">
                      {renderHighlightedText(script.description, descriptionMatches)}
                    </p>
                  </div>

                  <Link
                    href={`/scripts/${script.category}/${script.name}`}
                    className="shrink-0 flex items-center justify-center gap-2 border border-[var(--border)] hover:bg-[var(--surface-hover)] text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text)] px-4 py-2.5 rounded transition-colors"
                  >
                    <span>Inspect</span>
                  </Link>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-16 rounded-xl border border-[var(--border)] bg-[var(--surface)] text-xs text-[var(--text-muted)]">
              No scripts matching your terms were found. Try choosing a different matching algorithm.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

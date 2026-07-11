import { Script, SearchMode, SearchConfig, MatchSpan, MatchResult } from "./types";
import { matchSubstring } from "./modes/substring";
import { matchStrict } from "./modes/strict";
import { matchBroad } from "./modes/broad";
import { matchWholeWord } from "./modes/wholeWord";
import { matchFuzzy } from "./modes/fuzzy";

export interface ScriptSearchResult {
  script: Script;
  nameMatches: MatchSpan[];
  descriptionMatches: MatchSpan[];
  readmeMatches: MatchSpan[];
  score: number; // Higher is better
}

/**
 * Merge and deduplicate overlapping or adjacent matching index intervals
 */
export function mergeSpans(spans: MatchSpan[]): MatchSpan[] {
  if (spans.length <= 1) return spans;

  // Sort by start index ascending, then end index descending
  const sorted = [...spans].sort((a, b) => {
    if (a.start !== b.start) {
      return a.start - b.start;
    }
    return b.end - a.end;
  });

  const merged: MatchSpan[] = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i];
    const lastMerged = merged[merged.length - 1];

    if (current.start <= lastMerged.end) {
      // Overlapping or adjacent, merge them
      lastMerged.end = Math.max(lastMerged.end, current.end);
    } else {
      merged.push(current);
    }
  }

  return merged;
}

/**
 * Helper to execute a specific mode match
 */
function runModeMatch(
  mode: SearchMode,
  query: string,
  text: string,
  config: SearchConfig
): MatchResult {
  switch (mode) {
    case "Strict":
      return matchStrict(query, text, { ignoreSeparators: config.ignoreSeparators });
    case "Whole Word":
      return matchWholeWord(query, text);
    case "Broad":
      return matchBroad(query, text, { ignoreSeparators: config.ignoreSeparators });
    case "Substring":
      return matchSubstring(query, text);
    case "Fuzzy":
      return matchFuzzy(query, text, { fuzzyThreshold: config.fuzzyThreshold });
    default:
      return { text, matches: [] };
  }
}

/**
 * Run a multi-field search query across a list of scripts in a given mode
 */
export function searchScripts(
  query: string,
  scripts: Script[],
  mode: SearchMode,
  config: SearchConfig = {}
): ScriptSearchResult[] {
  if (!query || query.trim() === "") {
    return [];
  }

  const results: ScriptSearchResult[] = [];

  for (const script of scripts) {
    // Check match in each search field using the chosen mode
    const nameRes = runModeMatch(mode, query, script.name, config);
    const descRes = runModeMatch(mode, query, script.description, config);
    const readmeRes = runModeMatch(mode, query, script.readme || "", config);

    const hasNameMatch = nameRes.matches.length > 0;
    const hasDescMatch = descRes.matches.length > 0;
    const hasReadmeMatch = readmeRes.matches.length > 0;

    // If no match in any of the fields, skip this script
    if (!hasNameMatch && !hasDescMatch && !hasReadmeMatch) {
      continue;
    }

    // Merge overlapping spans
    const nameMatches = mergeSpans(nameRes.matches);
    const descriptionMatches = mergeSpans(descRes.matches);
    const readmeMatches = mergeSpans(readmeRes.matches);

    // Score calculation:
    // Boost name matches heavily, followed by description, and readme.
    // Also factor in match frequencies and mode-specific scores.
    let score = 0;

    if (hasNameMatch) {
      score += 1000;
      score += nameMatches.length * 100;
      if (nameRes.score !== undefined) {
        // For fuzzy: lower score returned by Fuse.js means closer match
        score += (1 - nameRes.score) * 500;
      }
    }
    if (hasDescMatch) {
      score += 300;
      score += descriptionMatches.length * 30;
      if (descRes.score !== undefined) {
        score += (1 - descRes.score) * 150;
      }
    }
    if (hasReadmeMatch) {
      score += 50;
      score += readmeMatches.length * 5;
      if (readmeRes.score !== undefined) {
        score += (1 - readmeRes.score) * 25;
      }
    }

    results.push({
      script,
      nameMatches,
      descriptionMatches,
      readmeMatches,
      score,
    });
  }

  // Sort by score descending (highest matches first)
  return results.sort((a, b) => b.score - a.score);
}

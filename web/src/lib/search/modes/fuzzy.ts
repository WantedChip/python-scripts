import Fuse from "fuse.js";
import { MatchResult, MatchSpan } from "../types";

export function matchFuzzy(
  query: string,
  text: string,
  config: { fuzzyThreshold?: number } = {}
): MatchResult {
  const matches: MatchSpan[] = [];
  if (!query || !text || query.length < 3 || query.length > text.length) {
    return { text, matches };
  }

  // threshold of 0.2 means 80% similarity (20% mismatch allowed)
  const threshold = config.fuzzyThreshold !== undefined ? config.fuzzyThreshold : 0.2;

  const fuse = new Fuse([text], {
    includeMatches: true,
    threshold: threshold,
    ignoreLocation: true, // find matches anywhere in the string
  });

  const results = fuse.search(query);
  if (results.length > 0 && results[0].matches && results[0].matches.length > 0) {
    const fuseMatches = results[0].matches[0];
    if (fuseMatches.indices) {
      fuseMatches.indices.forEach((indexPair) => {
        const start = indexPair[0];
        const end = indexPair[1] + 1; // convert inclusive to exclusive
        matches.push({ start, end });
      });
    }
    return {
      text,
      matches,
      score: results[0].score,
    };
  }

  return { text, matches };
}

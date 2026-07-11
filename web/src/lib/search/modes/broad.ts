import { MatchResult, MatchSpan } from "../types";

export function matchBroad(
  query: string,
  text: string,
  config: { ignoreSeparators?: boolean } = {}
): MatchResult {
  const matches: MatchSpan[] = [];
  if (!query || !text) {
    return { text, matches };
  }

  // 1. Build mapped character array and index mapping from original text
  let normTextMapped = "";
  const indexMap: number[] = [];
  const separatorRegex = /[\-_\.,\/\\]/;

  for (let i = 0; i < text.length; i++) {
    let char = text[i].normalize("NFKC").toLowerCase();
    if (char === " " || char === "\r" || char === "\n" || char === "\t") {
      char = " ";
      if (normTextMapped[normTextMapped.length - 1] === " ") {
        continue;
      }
    }
    if (config.ignoreSeparators && separatorRegex.test(char)) {
      continue;
    }
    normTextMapped += char;
    indexMap.push(i);
  }

  // 2. Tokenize query
  let normQuery = "";
  for (let i = 0; i < query.length; i++) {
    let char = query[i].normalize("NFKC").toLowerCase();
    if (char === " " || char === "\r" || char === "\n" || char === "\t") {
      char = " ";
      if (normQuery[normQuery.length - 1] === " ") {
        continue;
      }
    }
    if (config.ignoreSeparators && separatorRegex.test(char)) {
      continue;
    }
    normQuery += char;
  }

  const queryTokens = normQuery.split(" ").filter((t) => t.length > 0);
  if (queryTokens.length === 0) {
    return { text, matches };
  }

  // 3. Find matches for each token
  const tokenMatchesMap: { [token: string]: MatchSpan[] } = {};
  for (const token of queryTokens) {
    const tokenSpans: MatchSpan[] = [];
    let pos = normTextMapped.indexOf(token);
    while (pos !== -1) {
      tokenSpans.push({ start: pos, end: pos + token.length });
      pos = normTextMapped.indexOf(token, pos + 1);
    }

    if (tokenSpans.length === 0) {
      // REQUIRE ALL tokens present (no partial credit)
      return { text, matches: [] };
    }
    tokenMatchesMap[token] = tokenSpans;
  }

  // 4. Calculate proximity score (finding the minimum window containing all tokens)
  // Let's gather all occurrences as (pos, tokenIndex) pairs
  interface Occur {
    pos: number;
    tokenIdx: number;
    span: MatchSpan;
  }
  const occurrences: Occur[] = [];
  queryTokens.forEach((token, idx) => {
    tokenMatchesMap[token].forEach((span) => {
      occurrences.push({ pos: span.start, tokenIdx: idx, span });
    });
  });

  occurrences.sort((a, b) => a.pos - b.pos);

  // Sliding window to find min window containing all tokens
  let minWindow = Infinity;
  const currentTokenCounts: { [idx: number]: number } = {};
  let uniqueTokensInWindow = 0;
  let left = 0;

  for (let right = 0; right < occurrences.length; right++) {
    const rOccur = occurrences[right];
    currentTokenCounts[rOccur.tokenIdx] = (currentTokenCounts[rOccur.tokenIdx] || 0) + 1;
    if (currentTokenCounts[rOccur.tokenIdx] === 1) {
      uniqueTokensInWindow++;
    }

    while (uniqueTokensInWindow === queryTokens.length) {
      const windowSize = occurrences[right].pos + queryTokens[occurrences[right].tokenIdx].length - occurrences[left].pos;
      if (windowSize < minWindow) {
        minWindow = windowSize;
      }

      // Shrink window
      const lOccur = occurrences[left];
      currentTokenCounts[lOccur.tokenIdx]--;
      if (currentTokenCounts[lOccur.tokenIdx] === 0) {
        uniqueTokensInWindow--;
      }
      left++;
    }
  }

  const proximityScore = minWindow === Infinity ? 0 : 1 / minWindow;
  const frequencyScore = occurrences.length * 0.01;
  const totalScore = proximityScore + frequencyScore;

  // 5. Gather all matched spans and map back to original text offsets
  const tempSpans: MatchSpan[] = [];
  occurrences.forEach((occ) => {
    const start = indexMap[occ.span.start];
    const end = indexMap[occ.span.end - 1] + 1;
    tempSpans.push({ start, end });
  });

  return { text, matches: tempSpans, score: totalScore };
}

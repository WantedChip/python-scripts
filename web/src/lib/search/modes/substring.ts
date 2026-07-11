import { MatchResult, MatchSpan } from "../types";

export function matchSubstring(query: string, text: string): MatchResult {
  const matches: MatchSpan[] = [];
  if (!query || !text || query.length > text.length) {
    return { text, matches };
  }

  const q = query.toLowerCase();
  const t = text.toLowerCase();

  let pos = t.indexOf(q);
  while (pos !== -1) {
    matches.push({ start: pos, end: pos + q.length });
    pos = t.indexOf(q, pos + 1);
  }

  return { text, matches };
}

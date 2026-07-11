import { MatchResult, MatchSpan } from "../types";

export function matchWholeWord(query: string, text: string): MatchResult {
  const matches: MatchSpan[] = [];
  if (!query || !text || query.length > text.length) {
    return { text, matches };
  }

  // 1. Build normalized mapped text and index mapping
  let normTextMapped = "";
  const indexMap: number[] = [];

  for (let i = 0; i < text.length; i++) {
    let char = text[i].normalize("NFKC").toLowerCase();
    if (char === " " || char === "\r" || char === "\n" || char === "\t") {
      char = " ";
      if (normTextMapped[normTextMapped.length - 1] === " ") {
        continue;
      }
    }
    normTextMapped += char;
    indexMap.push(i);
  }

  // 2. Normalize query
  let normQuery = "";
  for (let i = 0; i < query.length; i++) {
    let char = query[i].normalize("NFKC").toLowerCase();
    if (char === " " || char === "\r" || char === "\n" || char === "\t") {
      char = " ";
      if (normQuery[normQuery.length - 1] === " ") {
        continue;
      }
    }
    normQuery += char;
  }

  normQuery = normQuery.trim();
  if (!normQuery || normQuery.length > normTextMapped.length) {
    return { text, matches };
  }

  // 3. Match and check boundaries
  const isWordChar = (char: string) => /[a-zA-Z0-9_]/.test(char);

  let pos = normTextMapped.indexOf(normQuery);
  while (pos !== -1) {
    const prevChar = pos > 0 ? normTextMapped[pos - 1] : "";
    const nextChar = pos + normQuery.length < normTextMapped.length ? normTextMapped[pos + normQuery.length] : "";

    const isPrevValid = !prevChar || !isWordChar(prevChar);
    const isNextValid = !nextChar || !isWordChar(nextChar);

    if (isPrevValid && isNextValid) {
      const start = indexMap[pos];
      const end = indexMap[pos + normQuery.length - 1] + 1;
      matches.push({ start, end });
    }

    pos = normTextMapped.indexOf(normQuery, pos + 1);
  }

  return { text, matches };
}

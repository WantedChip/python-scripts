import { MatchResult, MatchSpan } from "../types";

export function stripSeparators(str: string): { stripped: string; indexMap: number[] } {
  const indexMap: number[] = [];
  let stripped = "";
  const separatorRegex = /[\-_\.,\/\\]/; // - _ . , / \

  for (let i = 0; i < str.length; i++) {
    const char = str[i];
    if (!separatorRegex.test(char)) {
      stripped += char;
      indexMap.push(i);
    }
  }
  return { stripped, indexMap };
}

export function matchStrict(
  query: string,
  text: string,
  config: { ignoreSeparators?: boolean } = {}
): MatchResult {
  const matches: MatchSpan[] = [];
  if (!query || !text) {
    return { text, matches };
  }

  // Unicode NFKC normalization and collapse repeated spaces
  const normalize = (s: string) => s.normalize("NFKC").replace(/\s+/g, " ").trim().toLowerCase();

  const normalizedQuery = normalize(query);
  const normalizedText = normalize(text);

  if (config.ignoreSeparators) {
    const { stripped: qStripped } = stripSeparators(normalizedQuery);
    const { stripped: tStripped, indexMap } = stripSeparators(normalizedText);

    if (!qStripped || qStripped.length > tStripped.length) {
      return { text, matches };
    }

    let pos = tStripped.indexOf(qStripped);
    while (pos !== -1) {
      // Map back to normalizedText index offsets
      const normStart = indexMap[pos];
      const normEnd = indexMap[pos + qStripped.length - 1] + 1;

      // Now map normalizedText offsets back to original text offsets
      // Since normalizedText just collapsed spaces/lowercase/NFKC, let's map normalized indices.
      // Wait, is it simpler to normalize and map directly?
      // Actually, if we map directly from original text, it's even safer!
      // Let's write a direct mapper from original text to stripped text!
      pos = tStripped.indexOf(qStripped, pos + 1);
    }
  }

  // Let's make a robust mapper from original text to normalized/stripped text!
  // To avoid complex character mappings for NFKC, let's build the mapping from the original text directly.
  // Original text character-by-character mapping:
  const origToNormalizedMap: number[] = []; // maps index in normalized/stripped to index in original
  let processedText = "";
  
  // We normalize but we want to know which char in processedText maps to which char in original.
  // A simpler way: since we are case-insensitive and whitespace-collapsed, let's just match on original text
  // with a sliding pointer, or map the indices.
  // Let's build a character map:
  let normTextMapped = "";
  const indexMap: number[] = []; // maps normTextMapped index to original text index
  
  const separatorRegex = /[\-_\.,\/\\]/;

  for (let i = 0; i < text.length; i++) {
    let char = text[i].normalize("NFKC").toLowerCase();
    // Collapse spaces: if it's space and previous was space, skip it!
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

  // Now normalize the query exactly the same way
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
  
  normQuery = normQuery.trim();
  normTextMapped = normTextMapped.trim();

  if (!normQuery || normQuery.length > normTextMapped.length) {
    return { text, matches };
  }

  let pos = normTextMapped.indexOf(normQuery);
  while (pos !== -1) {
    const start = indexMap[pos];
    // Find the end index: indexMap[pos + length - 1] + 1
    const end = indexMap[pos + normQuery.length - 1] + 1;
    matches.push({ start, end });
    pos = normTextMapped.indexOf(normQuery, pos + 1);
  }

  return { text, matches };
}

export interface Script {
  name: string;
  category: string;
  path: string;
  description: string;
  readme: string;
  requirements: string[];
  hasTests: boolean;
  mainFile: string;
}

export interface MatchSpan {
  start: number;
  end: number;
}

export interface MatchResult {
  text: string;
  matches: MatchSpan[];
  score?: number; // Used for Fuzzy matching or custom ranking scores
}

export type SearchMode = "Broad" | "Strict" | "Fuzzy" | "Substring" | "Whole Word";

export interface SearchConfig {
  ignoreSeparators?: boolean;
  fuzzyThreshold?: number; // 0.0 to 1.0 (defaults to 0.2, i.e. 80% similarity, meaning distance of 0.2)
}

export type Tier = "S" | "A" | "B" | "C" | "D" | "Unranked";

/**
 * Calculates a script's Quality Tier (S -> D, or Unranked) based on public signals:
 * - Coverage:
 *   - 95-100% -> 2 pts
 *   - 90-94%  -> 1 pt
 *   - 80-89%  -> 0 pts  (clearing the mandatory floor earns nothing)
 *   - <80%    -> 0 pts  (below floor — should not occur in this repo)
 * - Dependencies:
 *   - 0 dependencies   -> +2 pts
 *   - 1-2 dependencies -> +1 pt
 *   - 3+ dependencies  -> +0 pts
 *
 * Total range: 0–4 pts → 5 live tiers:
 * - 4 pts -> S
 * - 3 pts -> A
 * - 2 pts -> B
 * - 1 pt  -> C
 * - 0 pts -> D
 *
 * Scripts missing the Quality line in their README are "Unranked" (separate state).
 */
export function calculateTier(
  coveragePct: number | null,
  depCount: number | null,
  unranked: boolean
): Tier {
  if (unranked || coveragePct === null || depCount === null) {
    return "Unranked";
  }

  let pts = 0;

  // 1. Coverage points (0 pts for merely clearing the 80% mandatory floor)
  if (coveragePct >= 95) {
    pts += 2;
  } else if (coveragePct >= 90) {
    pts += 1;
  }
  // 80-89%: +0 pts (floor clearance, not a quality signal)

  // 2. Dependency points
  if (depCount === 0) {
    pts += 2;
  } else if (depCount <= 2) {
    pts += 1;
  }

  // 3. Mapping (total range 0–4, all five tiers reachable)
  switch (pts) {
    case 4:
      return "S";
    case 3:
      return "A";
    case 2:
      return "B";
    case 1:
      return "C";
    default:
      // 0 pts: ranked but no exceptional signals → D
      return "D";
  }
}

/**
 * Returns a display style mapping for each tier level.
 * Leverages neutral/accent variables for premium dark terminal style.
 */
export function getTierStyle(tier: Tier): {
  color: string;
  borderColor: string;
  backgroundColor: string;
} {
  switch (tier) {
    case "S":
      return {
        color: "var(--accent)",
        borderColor: "var(--accent)",
        backgroundColor: "var(--accent-subtle)",
      };
    case "A":
      return {
        color: "var(--text)",
        borderColor: "var(--text)",
        backgroundColor: "rgba(255, 255, 255, 0.06)",
      };
    case "B":
      return {
        color: "var(--text-muted)",
        borderColor: "var(--border)",
        backgroundColor: "rgba(255, 255, 255, 0.03)",
      };
    case "C":
      return {
        color: "var(--text-dim)",
        borderColor: "var(--border-subtle)",
        backgroundColor: "transparent",
      };
    case "D":
      return {
        color: "var(--text-dim)",
        borderColor: "rgba(255, 255, 255, 0.05)",
        backgroundColor: "transparent",
      };
    default:
      return {
        color: "var(--text-dim)",
        borderColor: "var(--border-subtle)",
        backgroundColor: "rgba(255, 255, 255, 0.02)",
      };
  }
}

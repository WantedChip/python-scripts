export type Tier = "S" | "A" | "B" | "C" | "D" | "Unranked";

/**
 * Calculates a script's Quality Tier (S -> D, or Unranked) based on public signals:
 * - Coverage:
 *   - 95-100% -> 3 pts
 *   - 90-94%  -> 2 pts
 *   - 80-89%  -> 1 pt
 *   - <80% or unranked -> 0 pts
 * - Dependencies:
 *   - 0 dependencies  -> +2 pts
 *   - 1-2 dependencies -> +1 pt
 *   - 3+ dependencies  -> +0 pts
 *
 * Points to Tier mapping:
 * - 5 pts -> S
 * - 4 pts -> A
 * - 3 pts -> B
 * - 2 pts -> C
 * - 1 pt  -> D
 * - 0 pts / Unranked -> Unranked (shown as "Unranked" in the UI)
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

  // 1. Coverage points
  if (coveragePct >= 95) {
    pts += 3;
  } else if (coveragePct >= 90) {
    pts += 2;
  } else if (coveragePct >= 80) {
    pts += 1;
  }

  // 2. Dependency points
  if (depCount === 0) {
    pts += 2;
  } else if (depCount <= 2) {
    pts += 1;
  }

  // 3. Mapping
  switch (pts) {
    case 5:
      return "S";
    case 4:
      return "A";
    case 3:
      return "B";
    case 2:
      return "C";
    case 1:
      return "D";
    default:
      return "Unranked";
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

/**
 * Unit tests for the corrected tier scoring rubric.
 *
 * Scoring bands (0–4 pts → 5 live tiers):
 *   Coverage 95–100% → +2 pts
 *   Coverage 90–94%  → +1 pt
 *   Coverage 80–89%  → +0 pts  (merely clearing the mandatory floor)
 *   Dependencies 0   → +2 pts
 *   Dependencies 1–2 → +1 pt
 *   Dependencies 3+  → +0 pts
 *
 *   4 pts → S | 3 pts → A | 2 pts → B | 1 pt → C | 0 pts → D
 *   Unranked: scripts missing Quality line in README (separate from D)
 */
import { describe, it, expect } from "vitest";
import { calculateTier } from "./tier";

// ---------------------------------------------------------------------------
// Spec-required boundary examples
// ---------------------------------------------------------------------------
describe("spec boundary examples", () => {
  it("96% coverage + 0 deps → S  (2+2=4 pts)", () => {
    expect(calculateTier(96, 0, false)).toBe("S");
  });

  it("82% coverage + 3 deps → D  (0+0=0 pts)", () => {
    expect(calculateTier(82, 3, false)).toBe("D");
  });

  it("90% coverage + 1 dep → B   (1+1=2 pts)", () => {
    expect(calculateTier(90, 1, false)).toBe("B");
  });
});

// ---------------------------------------------------------------------------
// Coverage band boundaries (off-by-one guards)
// ---------------------------------------------------------------------------
describe("coverage band boundaries", () => {
  // 95% is the exact boundary between ≥95 (2 pts) and 90-94 (1 pt)
  it("95% coverage (>=95) earns 2 cov pts", () => {
    expect(calculateTier(95, 0, false)).toBe("S"); // 2+2=4
  });

  it("94% coverage (<95, >=90) earns 1 cov pt", () => {
    expect(calculateTier(94, 0, false)).toBe("A"); // 1+2=3
  });

  // 90% is the exact boundary between >=90 (1 pt) and 80-89 (0 pts)
  it("90% coverage (>=90) earns 1 cov pt", () => {
    expect(calculateTier(90, 0, false)).toBe("A"); // 1+2=3
  });

  it("89% coverage (<90, >=80) earns 0 cov pts", () => {
    expect(calculateTier(89, 0, false)).toBe("B"); // 0+2=2
  });

  // 80% is the mandatory floor — clearance earns nothing
  it("80% coverage earns 0 cov pts (floor clearance only)", () => {
    expect(calculateTier(80, 0, false)).toBe("B"); // 0+2=2
  });
});

// ---------------------------------------------------------------------------
// Dependency band boundaries
// ---------------------------------------------------------------------------
describe("dependency band boundaries", () => {
  it("0 deps earns 2 dep pts", () => {
    expect(calculateTier(95, 0, false)).toBe("S"); // 2+2=4
  });

  it("1 dep earns 1 dep pt", () => {
    expect(calculateTier(95, 1, false)).toBe("A"); // 2+1=3
  });

  it("2 deps earns 1 dep pt", () => {
    expect(calculateTier(95, 2, false)).toBe("A"); // 2+1=3
  });

  it("3 deps earns 0 dep pts", () => {
    expect(calculateTier(95, 3, false)).toBe("B"); // 2+0=2
  });

  it("10 deps earns 0 dep pts", () => {
    expect(calculateTier(95, 10, false)).toBe("B"); // 2+0=2
  });
});

// ---------------------------------------------------------------------------
// All 5 tiers reachable — none mathematically dead
// ---------------------------------------------------------------------------
describe("all tiers are reachable", () => {
  it("S tier is reachable: 95%+ cov, 0 deps (4 pts)", () => {
    expect(calculateTier(100, 0, false)).toBe("S");
  });

  it("A tier is reachable: 95%+ cov, 1 dep (3 pts)", () => {
    expect(calculateTier(97, 1, false)).toBe("A");
  });

  it("A tier is reachable: 90-94% cov, 0 deps (3 pts)", () => {
    expect(calculateTier(92, 0, false)).toBe("A");
  });

  it("B tier is reachable: 90-94% cov, 1-2 deps (2 pts)", () => {
    expect(calculateTier(91, 2, false)).toBe("B");
  });

  it("B tier is reachable: 80-89% cov, 0 deps (2 pts)", () => {
    expect(calculateTier(85, 0, false)).toBe("B");
  });

  it("C tier is reachable: 80-89% cov, 1-2 deps (1 pt)", () => {
    expect(calculateTier(83, 1, false)).toBe("C");
  });

  it("D tier is reachable: 80-89% cov, 3+ deps (0 pts)", () => {
    expect(calculateTier(81, 5, false)).toBe("D");
  });
});

// ---------------------------------------------------------------------------
// Unranked handling — independent of point bands
// ---------------------------------------------------------------------------
describe("Unranked is separate from D-Tier", () => {
  it("unranked=true returns Unranked regardless of coverage/deps", () => {
    expect(calculateTier(100, 0, true)).toBe("Unranked");
  });

  it("null coveragePct returns Unranked", () => {
    expect(calculateTier(null, 0, false)).toBe("Unranked");
  });

  it("null depCount returns Unranked", () => {
    expect(calculateTier(95, null, false)).toBe("Unranked");
  });

  it("both null returns Unranked", () => {
    expect(calculateTier(null, null, false)).toBe("Unranked");
  });

  // D-Tier is a distinct, live tier for ranked scripts with 0 quality bonus points
  it("ranked script with 0 bonus points → D, not Unranked", () => {
    expect(calculateTier(80, 3, false)).toBe("D");
  });
});

// ---------------------------------------------------------------------------
// Complete point matrix spot-check
// ---------------------------------------------------------------------------
describe("full point matrix", () => {
  const cases: [number, number, string][] = [
    // [coveragePct, depCount, expectedTier]
    [100, 0, "S"], // 2+2=4
    [95,  0, "S"], // 2+2=4
    [97,  1, "A"], // 2+1=3
    [97,  2, "A"], // 2+1=3
    [92,  0, "A"], // 1+2=3
    [97,  3, "B"], // 2+0=2
    [90,  1, "B"], // 1+1=2
    [90,  2, "B"], // 1+1=2
    [88,  0, "B"], // 0+2=2
    [80,  0, "B"], // 0+2=2
    [90,  3, "C"], // 1+0=1
    [88,  1, "C"], // 0+1=1
    [88,  2, "C"], // 0+1=1
    [80,  1, "C"], // 0+1=1
    [88,  3, "D"], // 0+0=0
    [80,  3, "D"], // 0+0=0
  ];

  cases.forEach(([cov, deps, expected]) => {
    it(`cov=${cov}% deps=${deps} → ${expected}`, () => {
      expect(calculateTier(cov, deps, false)).toBe(expected);
    });
  });
});

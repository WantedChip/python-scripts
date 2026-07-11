import React from "react";
import { calculateTier, getTierStyle, Tier } from "@/lib/tier";

interface TierBadgeProps {
  tier?: Tier;
  coveragePct?: number | null;
  depCount?: number | null;
  unranked?: boolean;
  size?: "sm" | "md";
}

export default function TierBadge({
  tier,
  coveragePct,
  depCount,
  unranked,
  size = "sm",
}: TierBadgeProps) {
  const resolvedTier =
    tier ||
    calculateTier(
      coveragePct !== undefined ? coveragePct : null,
      depCount !== undefined ? depCount : null,
      unranked !== undefined ? unranked : true
    );

  const style = getTierStyle(resolvedTier);
  const padding = size === "sm" ? "2px 6px" : "4px 10px";
  const fontSize = size === "sm" ? "10px" : "12px";

  return (
    <div
      style={{
        color: style.color,
        borderColor: style.borderColor,
        backgroundColor: style.backgroundColor,
        padding,
        fontSize,
        borderWidth: "1px",
        borderStyle: "solid",
        borderRadius: "4px",
        fontFamily: "var(--font-mono)",
        fontWeight: resolvedTier === "S" ? 700 : 500,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: 1,
        letterSpacing: "0.02em",
      }}
      title={
        resolvedTier === "Unranked"
          ? "Unranked (Quality score not specified in README)"
          : `Tier ${resolvedTier} Script`
      }
    >
      {resolvedTier === "Unranked" ? "UNRANKED" : `${resolvedTier}-TIER`}
    </div>
  );
}

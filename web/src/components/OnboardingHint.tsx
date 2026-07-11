"use client";

import React, { useState, useEffect } from "react";
import { X, Sparkles } from "lucide-react";

export default function OnboardingHint() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem("pyscripts-hint-dismissed");
    if (!dismissed) {
      setVisible(true);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem("pyscripts-hint-dismissed", "true");
    setVisible(false);
  };

  if (!visible) return null;

  // Detect OS for shortcut hint
  const isMac = typeof window !== "undefined" && navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  const shortcutText = isMac ? "⌘K" : "Ctrl+K";

  return (
    <div className="fixed bottom-4 right-4 z-40 max-w-sm w-[calc(100vw-2rem)] bg-[var(--surface-raised)] border border-[var(--border)] rounded-lg p-4 shadow-2xl flex gap-3 animate-in slide-in-from-bottom-5 fade-in duration-300">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--accent-subtle)] text-[var(--accent)]">
        <Sparkles className="h-4 w-4" />
      </div>
      <div className="flex-1 flex flex-col gap-1 pr-6">
        <h4 className="text-xs font-semibold text-[var(--text)]">Search Monorepo Instantly</h4>
        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          Press <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface)] border border-[var(--border)] font-mono text-[10px] text-[var(--text)]">{shortcutText}</kbd> on any page to find scripts, navigate categories, or download folder zip packages.
        </p>
      </div>
      <button
        onClick={handleDismiss}
        className="absolute top-3 right-3 text-[var(--text-dim)] hover:text-[var(--text)] transition-colors cursor-pointer"
        aria-label="Dismiss hint"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

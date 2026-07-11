"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Terminal, Search, HelpCircle, Home, FolderOpen, ArrowRight, Check, Download } from "lucide-react";
import scriptsData from "@/data/scripts.json";
import { searchScripts } from "@/lib/search";
import { Script } from "@/lib/search/types";

interface CommandItem {
  id: string;
  title: string;
  subtitle: string;
  action: () => void;
  icon: React.ReactNode;
  category?: string;
}

export default function CommandPalette() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [copiedFeedback, setCopiedFeedback] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Listen for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Handle clicking outside the modal
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  // Focus input on open
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Helper to trigger direct downloading
  const triggerDownload = (path: string, mode: "file" | "zip", filename: string) => {
    const link = document.createElement("a");
    link.href = `/api/download?path=${encodeURIComponent(path)}&mode=${mode}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  // Helper to copy text to clipboard with temporary feedback
  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedFeedback(id);
      setTimeout(() => setCopiedFeedback(null), 2000);
    });
  };

  // Compile list of possible command options based on user query
  const getCommands = (): CommandItem[] => {
    const scripts = scriptsData as Script[];
    const items: CommandItem[] = [];
    const normalizedQuery = query.toLowerCase().trim();

    // Default suggestions when query is empty
    if (!normalizedQuery) {
      // General navigation helper
      items.push({
        id: "nav-home",
        title: "home",
        subtitle: "Navigate to PyScripts Homepage",
        icon: <Home className="h-4 w-4" />,
        action: () => {
          router.push("/");
          setIsOpen(false);
        },
      });
      items.push({
        id: "nav-guide",
        title: "help",
        subtitle: "Open Guide and Onboarding Docs",
        icon: <HelpCircle className="h-4 w-4" />,
        action: () => {
          router.push("/guide");
          setIsOpen(false);
        },
      });

      // CD category triggers
      const categories = Array.from(new Set(scripts.map((s) => s.category)));
      categories.forEach((cat) => {
        items.push({
          id: `cd-${cat}`,
          title: `cd ${cat}`,
          subtitle: `Browse all scripts in ${cat} category`,
          icon: <FolderOpen className="h-4 w-4" />,
          action: () => {
            router.push(`/browse/${cat}`);
            setIsOpen(false);
          },
        });
      });

      return items;
    }

    // Match explicit command formats first
    if (normalizedQuery.startsWith("open ")) {
      const subQuery = normalizedQuery.slice(5).trim();
      const matched = searchScripts(subQuery, scripts, "Broad");
      matched.forEach(({ script }) => {
        items.push({
          id: `open-${script.name}`,
          title: `open ${script.name}`,
          subtitle: `Go to ${script.name} detail page`,
          icon: <ArrowRight className="h-4 w-4" />,
          action: () => {
            router.push(`/scripts/${script.category}/${script.name}`);
            setIsOpen(false);
          },
        });
      });
      return items;
    }

    if (normalizedQuery.startsWith("cd ") || normalizedQuery.startsWith("browse ")) {
      const subQuery = normalizedQuery.startsWith("cd ")
        ? normalizedQuery.slice(3).trim()
        : normalizedQuery.slice(7).trim();
      const categories = Array.from(new Set(scripts.map((s) => s.category)));
      categories
        .filter((cat) => cat.includes(subQuery))
        .forEach((cat) => {
          items.push({
            id: `cd-${cat}`,
            title: `cd ${cat}`,
            subtitle: `Browse all scripts in ${cat} category`,
            icon: <FolderOpen className="h-4 w-4" />,
            action: () => {
              router.push(`/browse/${cat}`);
              setIsOpen(false);
            },
          });
        });
      return items;
    }

    if (normalizedQuery.startsWith("download ")) {
      const subQuery = normalizedQuery.slice(9).trim();
      const matched = searchScripts(subQuery, scripts, "Broad");
      matched.forEach(({ script }) => {
        items.push({
          id: `dl-py-${script.name}`,
          title: `download ${script.name} (.py)`,
          subtitle: `Download single Python script file directly`,
          icon: <Download className="h-4 w-4 text-[var(--accent)]" />,
          action: () => triggerDownload(script.path, "file", script.mainFile),
        });
        items.push({
          id: `dl-zip-${script.name}`,
          title: `download ${script.name} (.zip)`,
          subtitle: `Download entire script directory in ZIP archive`,
          icon: <Download className="h-4 w-4 text-[var(--success)]" />,
          action: () => triggerDownload(script.path, "zip", `${script.name}.zip`),
        });
      });
      return items;
    }

    if (normalizedQuery.startsWith("copy install ")) {
      const subQuery = normalizedQuery.slice(13).trim();
      const matched = searchScripts(subQuery, scripts, "Broad");
      matched.forEach(({ script }) => {
        const cmd = "pip install -r requirements.txt";
        items.push({
          id: `copy-${script.name}`,
          title: `copy install ${script.name}`,
          subtitle: copiedFeedback === `copy-${script.name}` ? "Copied to clipboard!" : `Copy to clipboard: "${cmd}"`,
          icon: copiedFeedback === `copy-${script.name}` ? <Check className="h-4 w-4 text-[var(--success)]" /> : <Terminal className="h-4 w-4" />,
          action: () => handleCopy(cmd, `copy-${script.name}`),
        });
      });
      return items;
    }

    if (normalizedQuery === "help") {
      items.push({
        id: "nav-guide",
        title: "help",
        subtitle: "Open Guide and Onboarding Docs",
        icon: <HelpCircle className="h-4 w-4" />,
        action: () => {
          router.push("/guide");
          setIsOpen(false);
        },
      });
      return items;
    }

    if (normalizedQuery === "home") {
      items.push({
        id: "nav-home",
        title: "home",
        subtitle: "Navigate to PyScripts Homepage",
        icon: <Home className="h-4 w-4" />,
        action: () => {
          router.push("/");
          setIsOpen(false);
        },
      });
      return items;
    }

    // Generic search: Broad matching script names with actions fallback
    const matched = searchScripts(normalizedQuery, scripts, "Broad");
    
    // If Broad returns nothing, fall back to Fuzzy matching (minimum query size 3)
    let finalMatched = matched;
    if (finalMatched.length === 0 && normalizedQuery.length >= 3) {
      finalMatched = searchScripts(normalizedQuery, scripts, "Fuzzy");
    }

    finalMatched.forEach(({ script }) => {
      // 1. Navigation Option
      items.push({
        id: `open-${script.name}`,
        title: `open ${script.name}`,
        subtitle: script.description,
        icon: <ArrowRight className="h-4 w-4" />,
        action: () => {
          router.push(`/scripts/${script.category}/${script.name}`);
          setIsOpen(false);
        },
      });
      // 2. Download Options
      items.push({
        id: `dl-py-${script.name}`,
        title: `download ${script.name} (.py)`,
        subtitle: `Direct download single file ${script.mainFile}`,
        icon: <Download className="h-4 w-4 text-[var(--accent)]" />,
        action: () => triggerDownload(script.path, "file", script.mainFile),
      });
      // 3. Clipboard Option
      const cmd = "pip install -r requirements.txt";
      items.push({
        id: `copy-${script.name}`,
        title: `copy install ${script.name}`,
        subtitle: copiedFeedback === `copy-${script.name}` ? "Copied to clipboard!" : `Copy command: "${cmd}"`,
        icon: copiedFeedback === `copy-${script.name}` ? <Check className="h-4 w-4 text-[var(--success)]" /> : <Terminal className="h-4 w-4" />,
        action: () => handleCopy(cmd, `copy-${script.name}`),
      });
    });

    return items;
  };

  const currentCommands = getCommands();

  // Reset index when commands change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Handle arrow navigation and selection executing
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % currentCommands.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + currentCommands.length) % currentCommands.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (currentCommands[selectedIndex]) {
        currentCommands[selectedIndex].action();
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/70 backdrop-blur-xs p-4">
      <div
        ref={containerRef}
        className="w-full max-w-lg bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-2xl overflow-hidden font-mono text-sm flex flex-col max-h-[70vh] animate-in zoom-in-95 duration-100"
      >
        {/* Terminal Query Input Box */}
        <div className="flex items-center border-b border-[var(--border)] px-4 py-3 bg-[var(--surface-raised)]">
          <span className="text-[var(--accent)] font-bold mr-2 shrink-0">&gt;</span>
          <input
            ref={inputRef}
            type="text"
            placeholder="Type a command or search scripts..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent border-none text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none w-full"
          />
          <span className="text-[var(--text-dim)] text-[10px] shrink-0">ESC to close</span>
        </div>

        {/* Suggestion list results */}
        <div className="flex-1 overflow-y-auto p-2 scrollbar">
          {currentCommands.length > 0 ? (
            currentCommands.map((cmd, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={cmd.id}
                  onClick={cmd.action}
                  className={`w-full text-left flex items-start gap-3 px-3 py-2.5 rounded-md transition-colors cursor-pointer ${
                    isSelected ? "bg-[var(--surface-hover)]" : "bg-transparent"
                  }`}
                >
                  <div
                    className={`mt-0.5 shrink-0 ${
                      isSelected ? "text-[var(--accent)]" : "text-[var(--text-muted)]"
                    }`}
                  >
                    {cmd.icon}
                  </div>
                  <div className="flex-1 flex flex-col gap-0.5">
                    <span
                      className={`font-semibold text-xs leading-none ${
                        isSelected ? "text-[var(--text)] font-bold" : "text-[var(--text-muted)]"
                      }`}
                    >
                      {cmd.title}
                    </span>
                    <span className="text-[10px] text-[var(--text-dim)] leading-tight">
                      {cmd.subtitle}
                    </span>
                  </div>
                  {isSelected && (
                    <span className="text-[10px] text-[var(--accent)] shrink-0 self-center font-bold">
                      ⏎ Enter
                    </span>
                  )}
                </button>
              );
            })
          ) : (
            <div className="text-center py-6 text-xs text-[var(--text-dim)]">
              No matching commands or scripts found.
            </div>
          )}
        </div>

        {/* Console status footer */}
        <div className="border-t border-[var(--border)] px-4 py-2 bg-[var(--surface-raised)] text-[10px] text-[var(--text-dim)] flex justify-between shrink-0">
          <span>Usage: open, cd, download, copy install, help</span>
          <span>⌥ ↑↓ navigation</span>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

/* ─── Phase 1: Raw boot log lines ─────────────────────────────────────────── */
const BOOT_LINES: { text: string; delay: number; color?: string; bold?: boolean }[] = [
  { text: "PyScripts OS  v2.1.0-release  #1 SMP", delay: 0, color: "#7c3aed", bold: true },
  { text: "Copyright (c) WantedChip. All rights reserved.", delay: 70, color: "#71717a" },
  { text: "", delay: 110 },
  { text: "BIOS-e820: [mem 0x0000000000000000-0x000000000009efff] usable", delay: 170, color: "#52525b" },
  { text: "BIOS-e820: [mem 0x00000000000f0000-0x00000000000fffff] reserved", delay: 220, color: "#52525b" },
  { text: "", delay: 270 },
  { text: "[    0.000000] Initializing cgroup subsys cpuset", delay: 330, color: "#a1a1aa" },
  { text: "[    0.000000] Linux version 6.8.0-pyscripts (gcc version 13.2.0)", delay: 400, color: "#a1a1aa" },
  { text: "[    0.000000] Command line: BOOT_IMAGE=/vmlinuz-6.8.0-pyscripts root=/dev/scripts", delay: 470, color: "#a1a1aa" },
  { text: "[    0.012384] ACPI: Core revision 20240101", delay: 550, color: "#a1a1aa" },
  { text: "[    0.042391] Loading hardware abstraction layer ...", delay: 630, color: "#a1a1aa" },
  { text: "[    0.118203] Mounting script filesystem [ext4]", delay: 720, color: "#a1a1aa" },
  { text: "[    0.204871] Loading script registry ...", delay: 810, color: "#a1a1aa" },
  { text: "[    0.311042] Initializing Python runtime environment [3.12.x]", delay: 900, color: "#a1a1aa" },
  { text: "[    0.402918] Verifying script integrity checksums ...", delay: 1000, color: "#a1a1aa" },
  { text: "", delay: 1060 },
  { text: "[    0.512034] pylint      ........................................  [ OK ]", delay: 1140, color: "#22c55e" },
  { text: "[    0.601289] mypy strict ........................................  [ OK ]", delay: 1280, color: "#22c55e" },
  { text: "[    0.701034] bandit      ........................................  [ OK ]", delay: 1420, color: "#22c55e" },
  { text: "[    0.804521] coverage    ........................................ [ OK ]", delay: 1560, color: "#22c55e" },
  { text: "", delay: 1640 },
  { text: "[    0.910023] Mounting read-write script store ...", delay: 1720, color: "#a1a1aa" },
  { text: "[    1.012984] Activating network interface [eth0]", delay: 1860, color: "#a1a1aa" },
  { text: "[    1.120041] Connecting to script repository ...", delay: 2000, color: "#a1a1aa" },
  { text: "[    1.234590] Syncing package index ...", delay: 2140, color: "#a1a1aa" },
  { text: "[    1.345021] Loading dependency resolver ...", delay: 2280, color: "#a1a1aa" },
  { text: "", delay: 2360 },
  { text: "[    1.456012] Starting PyScripts daemon ...", delay: 2440, color: "#a1a1aa" },
  { text: "[    1.567840] Service manager: ready.", delay: 2600, color: "#a1a1aa" },
  { text: "[    1.678920] Session manager: initialized.", delay: 2760, color: "#a1a1aa" },
  { text: "[    1.789234] udev[231]: starting version 3.2.14", delay: 2900, color: "#a1a1aa" },
  { text: "[    1.893012] udev[231]: listening on socket", delay: 3020, color: "#a1a1aa" },
  { text: "", delay: 3100 },
  { text: "[  OK  ] Started PyScripts Daemon.", delay: 3180, color: "#22c55e" },
  { text: "[  OK  ] Reached target Multi-User System.", delay: 3320, color: "#22c55e" },
  { text: "[  OK  ] Reached target Graphical Interface.", delay: 3460, color: "#22c55e" },
  { text: "", delay: 3560 },
  { text: "PyScripts OS v2.1.0 pyscripts tty1", delay: 3700, color: "#fafafa", bold: true },
  { text: "", delay: 3780 },
];

const BOOT_DONE_DELAY = 3780;      // when last line appears
const TERMINAL_PHASE_DELAY = 4300; // fade to terminal after this ms

/* ─── Known commands ──────────────────────────────────────────────────────── */
const COMMANDS: Record<
  string,
  { action: "navigate" | "print"; target?: string; output?: string[] }
> = {
  home: { action: "navigate", target: "/" },
  help: {
    action: "print",
    output: [
      "Available commands:",
      "  home    — Open the PyScripts library",
      "  help    — Show this help message",
      "  clear   — Clear the terminal",
      "  version — Show system version",
    ],
  },
  clear: { action: "print", output: ["__CLEAR__"] },
  version: {
    action: "print",
    output: ["PyScripts OS v2.1.0-release", "Python runtime: 3.12.x"],
  },
};

interface TerminalLine {
  id: number;
  content: string;
  type: "output" | "input" | "error";
  color?: string;
  bold?: boolean;
}

let lineIdCounter = 0;
function mkLine(
  content: string,
  type: TerminalLine["type"] = "output",
  color?: string,
  bold?: boolean
): TerminalLine {
  return { id: lineIdCounter++, content, type, color, bold };
}

/* ═══════════════════════════════════════════════════════════════════════════ */

export default function BootPage() {
  const router = useRouter();

  /* ── Phase control ────────────────────────────────────────────────────── */
  // "boot"     → raw fullscreen log scrolling
  // "terminal" → interactive terminal (crossfade via CSS transitions)
  const [phase, setPhase] = useState<"boot" | "terminal">("boot");

  /* ── Boot phase state ─────────────────────────────────────────────────── */
  const [bootLines, setBootLines] = useState<
    { text: string; color?: string; bold?: boolean }[]
  >([]);
  const [showCursor, setShowCursor] = useState(true);
  const bootRef = useRef<HTMLDivElement>(null);

  /* ── Terminal phase state ─────────────────────────────────────────────── */
  const [termLines, setTermLines] = useState<TerminalLine[]>([
    mkLine("Type  help  to see available commands, or  home  to open the library.", "output", "#71717a"),
  ]);
  const [inputValue, setInputValue] = useState("");
  const [cmdHistory, setCmdHistory] = useState<string[]>([]);
  const [, setHistoryIndex] = useState(-1);
  const [isNavigating, setIsNavigating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  /* ── Lock body scroll while overlay is active ─────────────────────────── */
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  /* ── Run boot sequence ────────────────────────────────────────────────── */
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];

    BOOT_LINES.forEach((line) => {
      const t = setTimeout(() => {
        setBootLines((prev) => [...prev, { text: line.text, color: line.color, bold: line.bold }]);
        if (bootRef.current) {
          bootRef.current.scrollTop = bootRef.current.scrollHeight;
        }
      }, line.delay);
      timers.push(t);
    });

    // Hide blinking cursor just before terminal appears
    const t1 = setTimeout(() => setShowCursor(false), BOOT_DONE_DELAY + 200);
    timers.push(t1);

    // Directly switch to terminal — both divs' CSS transitions fire together
    // creating a smooth crossfade with no gap.
    const t3 = setTimeout(() => {
      setPhase("terminal");
      setTimeout(() => inputRef.current?.focus(), 80);
    }, TERMINAL_PHASE_DELAY);
    timers.push(t3);

    return () => timers.forEach(clearTimeout);
  }, []);

  /* ── Keep terminal scrolled to bottom ────────────────────────────────── */
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [termLines]);

  /* ── Execute a command ────────────────────────────────────────────────── */
  const runCommand = useCallback(
    (raw: string) => {
      const cmd = raw.trim().toLowerCase();
      setTermLines((prev) => [
        ...prev,
        mkLine(`python scripts> ${raw}`, "input", "#fafafa"),
      ]);
      if (!cmd) return;

      setCmdHistory((h) => [raw, ...h]);
      setHistoryIndex(-1);

      const def = COMMANDS[cmd];
      if (!def) {
        setTermLines((prev) => [
          ...prev,
          mkLine(
            `'${cmd}' is not recognized. Type 'help' for available commands.`,
            "error",
            "#ef4444"
          ),
        ]);
        return;
      }

      if (def.action === "navigate" && def.target) {
        setIsNavigating(true);
        setTermLines((prev) => [
          ...prev,
          mkLine("Launching PyScripts library …", "output", "#7c3aed"),
        ]);
        document.cookie = "pyscripts_booted=1; path=/; SameSite=Lax";
        setTimeout(() => router.push(def.target!), 600);
        return;
      }

      if (def.action === "print" && def.output) {
        if (def.output[0] === "__CLEAR__") {
          setTermLines([]);
          return;
        }
        setTermLines((prev) => [
          ...prev,
          ...def.output!.map((l) => mkLine(l, "output", "#a1a1aa")),
        ]);
      }
    },
    [router]
  );

  /* ── Key handler ──────────────────────────────────────────────────────── */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        runCommand(inputValue);
        setInputValue("");
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHistoryIndex((hi) => {
          const next = Math.min(hi + 1, cmdHistory.length - 1);
          setInputValue(cmdHistory[next] ?? "");
          return next;
        });
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHistoryIndex((hi) => {
          const next = Math.max(hi - 1, -1);
          setInputValue(next === -1 ? "" : (cmdHistory[next] ?? ""));
          return next;
        });
      }
    },
    [inputValue, cmdHistory, runCommand]
  );

  /* ── Focus input on click ─────────────────────────────────────────────── */
  const focusInput = useCallback(() => {
    if (!isNavigating) inputRef.current?.focus();
  }, [isNavigating]);

  /* ═══════════════════════════════════════════════════════════════════════ */
  return (
    <>
      {/* Permanent black backdrop — always covers the site behind the phases */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9998,
          background: "#000",
          pointerEvents: "none",
        }}
      />

      {/* ── PHASE 1: Raw fullscreen boot log ─────────────────────────────── */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          background: "#000",
          padding: "1.5rem 2rem",
          boxSizing: "border-box",
          overflowY: "auto",
          overflowX: "hidden",
          fontFamily: "'Courier New', 'Lucida Console', monospace",
          opacity: phase === "boot" ? 1 : 0,
          pointerEvents: phase === "boot" ? "auto" : "none",
          transition: "opacity 0.7s ease",
        }}
        ref={bootRef}
      >
        {bootLines.map((line, i) => (
          <div
            key={i}
            style={{
              fontSize: "clamp(0.75rem, 1.5vw, 0.9rem)",
              lineHeight: "1.65",
              color: line.color ?? "#a1a1aa",
              fontWeight: line.bold ? 700 : 400,
              letterSpacing: "0.01em",
              whiteSpace: "pre",
              minHeight: "1.4em",
            }}
          >
            {line.text || "\u00A0"}
          </div>
        ))}
        {/* Blinking block cursor */}
        {showCursor && (
          <span
            style={{
              display: "inline-block",
              width: "0.6rem",
              height: "1rem",
              background: "#a1a1aa",
              animation: "blink 1s step-start infinite",
              verticalAlign: "bottom",
              marginTop: "0.1rem",
            }}
          />
        )}
      </div>

      {/* ── PHASE 2: Full-screen terminal ────────────────────────────────── */}
      <div
        onClick={focusInput}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          background: "#09090b",
          display: "flex",
          flexDirection: "column",
          fontFamily: "var(--font-geist-mono, 'Courier New', monospace)",
          opacity: phase === "terminal" ? 1 : 0,
          pointerEvents: phase === "terminal" ? "auto" : "none",
          transition: "opacity 0.7s ease",
          cursor: "default",
        }}
      >
        {/* ── Top bar ─────────────────────────────────────────────────── */}
        <div
          style={{
            background: "#18181b",
            borderBottom: "1px solid #27272a",
            padding: "0.6rem 1.25rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            flexShrink: 0,
          }}
        >
          {/* Traffic lights */}
          <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
          <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#f59e0b", display: "inline-block" }} />
          <span style={{ width: 12, height: 12, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />

          {/* Title */}
          <span
            style={{
              position: "absolute",
              left: "50%",
              transform: "translateX(-50%)",
              fontSize: "0.8rem",
              color: "#71717a",
              letterSpacing: "0.06em",
              fontFamily: "inherit",
              userSelect: "none",
            }}
          >
            PyScripts OS — terminal
          </span>

          {/* Right: version badge */}
          <span
            style={{
              marginLeft: "auto",
              fontSize: "0.7rem",
              color: "#3f3f46",
              fontFamily: "inherit",
            }}
          >
            v2.1.0
          </span>
        </div>

        {/* ── Terminal body ────────────────────────────────────────────── */}
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            padding: "1.5rem 2rem",
            overflowY: "auto",
            scrollBehavior: "smooth",
            boxSizing: "border-box",
          }}
        >
          {/* Subtle violet glow at the top */}
          <div
            aria-hidden
            style={{
              position: "absolute",
              top: 0,
              left: "50%",
              transform: "translateX(-50%)",
              width: "60%",
              height: "180px",
              background: "radial-gradient(ellipse at top, rgba(124,58,237,0.07) 0%, transparent 70%)",
              pointerEvents: "none",
            }}
          />

          {/* Boot summary at top of terminal */}
          <div style={{ marginBottom: "1.5rem", paddingBottom: "1rem", borderBottom: "1px solid #27272a" }}>
            <span style={{ color: "#7c3aed", fontWeight: 700, fontSize: "0.875rem" }}>PyScripts OS</span>
            <span style={{ color: "#71717a", fontSize: "0.8rem" }}> v2.1.0-release — system ready</span>
          </div>

          {/* History lines */}
          {termLines.map((line) => (
            <div
              key={line.id}
              style={{
                fontSize: "0.9rem",
                lineHeight: "1.7",
                color: line.color ?? "#a1a1aa",
                fontWeight: line.bold ? 700 : 400,
                fontFamily: "inherit",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                minHeight: "1.5em",
              }}
            >
              {line.content || "\u00A0"}
            </div>
          ))}

          {/* Input row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              marginTop: "0.25rem",
              gap: "0.35rem",
            }}
          >
            <span
              style={{
                color: "#7c3aed",
                fontWeight: 700,
                fontSize: "0.9rem",
                whiteSpace: "nowrap",
                flexShrink: 0,
                userSelect: "none",
              }}
            >
              python scripts&gt;
            </span>

            {/* Hidden real input — captures keystrokes */}
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isNavigating}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              aria-label="terminal input"
              style={{
                position: "absolute",
                opacity: 0,
                width: 0,
                height: 0,
                pointerEvents: isNavigating ? "none" : "auto",
              }}
            />

            {/* Visual typed text + cursor */}
            <span
              style={{
                fontSize: "0.9rem",
                color: "#fafafa",
                lineHeight: "1.7",
                display: "inline-flex",
                alignItems: "center",
                letterSpacing: "0.01em",
              }}
            >
              {inputValue}
              <span
                style={{
                  display: "inline-block",
                  width: "0.55rem",
                  height: "1.1em",
                  background: isNavigating ? "transparent" : "#7c3aed",
                  marginLeft: "2px",
                  animation: isNavigating ? "none" : "blink 1s step-start infinite",
                  verticalAlign: "bottom",
                  borderRadius: "1px",
                  flexShrink: 0,
                }}
              />
            </span>
          </div>
        </div>

        {/* ── Hint bar ─────────────────────────────────────────────────── */}
        <div
          style={{
            background: "#18181b",
            borderTop: "1px solid #27272a",
            padding: "0.5rem 2rem",
            display: "flex",
            gap: "2rem",
            flexWrap: "wrap",
            flexShrink: 0,
          }}
        >
          {[
            { key: "home", desc: "open library" },
            { key: "help", desc: "list commands" },
            { key: "clear", desc: "clear screen" },
            { key: "version", desc: "system info" },
          ].map(({ key, desc }) => (
            <span
              key={key}
              style={{ fontSize: "0.75rem", color: "#71717a", fontFamily: "inherit", userSelect: "none" }}
            >
              <span
                style={{
                  color: "#7c3aed",
                  fontWeight: 600,
                  marginRight: "0.35rem",
                  cursor: "pointer",
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  setInputValue(key);
                  inputRef.current?.focus();
                }}
              >
                {key}
              </span>
              {desc}
            </span>
          ))}
        </div>
      </div>

      {/* ── Global keyframes ─────────────────────────────────────────────── */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0; }
        }
      `}</style>
    </>
  );
}

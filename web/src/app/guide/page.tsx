import type { Metadata } from "next";
import Link from "next/link";
import { Keyboard, Search, Download, ExternalLink, ArrowRight } from "lucide-react";

export const metadata: Metadata = {
  title: "Guide",
  description: "Learn how to use PyScripts command palette, search engine modes, and download managers.",
};

export default function GuidePage() {
  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-4xl mx-auto flex flex-col gap-10">
        {/* Header */}
        <div className="flex flex-col gap-3 border-b border-[var(--border)] pb-8">
          <div className="flex items-center gap-2 font-mono text-xs text-[var(--accent)]">
            <span>$</span>
            <span>pyscripts --show-manual</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--text)]">User Guide</h1>
          <p className="text-sm text-[var(--text-muted)] max-w-2xl leading-relaxed">
            Welcome to PyScripts. Learn how to search, download, and navigate our repository of standalone Python CLI utilities.
          </p>
        </div>

        {/* Section 1: Command Palette */}
        <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-md flex flex-col gap-5">
          <h2 className="text-lg font-bold text-[var(--text)] font-mono flex items-center gap-2.5">
            <Keyboard className="h-5 w-5 text-[var(--accent)]" />
            <span>1. The Command Palette</span>
          </h2>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            The command palette is the quickest way to navigate the site, inspect scripts, or trigger direct downloads. It can be opened from any page using your keyboard.
          </p>
          
          <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4">
            <h3 className="text-xs font-semibold text-[var(--text)] font-mono">Keyboard Shortcuts</h3>
            <div className="flex gap-4 text-xs font-mono">
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)]">macOS:</span>
                <kbd className="px-2 py-1 rounded bg-[var(--surface-raised)] border border-[var(--border)] text-[11px] text-[var(--text)]">⌘ + K</kbd>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-dim)]">Windows/Linux:</span>
                <kbd className="px-2 py-1 rounded bg-[var(--surface-raised)] border border-[var(--border)] text-[11px] text-[var(--text)]">Ctrl + K</kbd>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4">
            <h3 className="text-xs font-semibold text-[var(--text)] font-mono">Console Command Layout</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs border border-[var(--border)]">
                <thead>
                  <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                    <th className="p-2.5 text-left font-mono font-semibold text-[var(--text)]">Syntax</th>
                    <th className="p-2.5 text-left font-mono font-semibold text-[var(--text)]">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">open &lt;script&gt;</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Navigate to the detailed documentation page for the script.</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">cd &lt;category&gt;</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Open the browse catalog page filtered by that category.</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">download &lt;script&gt;</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Download the script file (.py) or package zip folder directly.</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">copy install &lt;script&gt;</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Copy pip installation commands directly to your clipboard.</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">help</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Jump back to this guide page.</td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-mono text-[var(--accent)]">home</td>
                    <td className="p-2.5 text-[var(--text-muted)]">Navigate directly back to the landing homepage.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Section 2: Search Modes */}
        <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-md flex flex-col gap-5">
          <h2 className="text-lg font-bold text-[var(--text)] font-mono flex items-center gap-2.5">
            <Search className="h-5 w-5 text-[var(--success)]" />
            <span>2. Matching Algorithms</span>
          </h2>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            The search engine runs across three primary script metadata fields: **name**, **description**, and **README contents**. Five distinct search modes are available:
          </p>

          <div className="overflow-x-auto border border-[var(--border)] rounded-lg">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                  <th className="p-3 text-left font-mono font-semibold text-[var(--text)]">Mode</th>
                  <th className="p-3 text-left font-mono font-semibold text-[var(--text)]">Details</th>
                  <th className="p-3 text-left font-mono font-semibold text-[var(--text)]">Example Output</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)] font-mono text-[11px]">
                <tr>
                  <td className="p-3 font-bold text-[var(--accent)]">Broad</td>
                  <td className="p-3 text-[var(--text-muted)]">Tokenizes terms; requires all tokens present in text. Matches in any order.</td>
                  <td className="p-3"><code className="text-[var(--text)] bg-[var(--surface-raised)] px-1 rounded">&quot;red apple&quot;</code> matches &quot;apple that is red&quot;</td>
                </tr>
                <tr>
                  <td className="p-3 font-bold text-[var(--accent)]">Strict</td>
                  <td className="p-3 text-[var(--text-muted)]">Matches the exact case-insensitive normalized substring.</td>
                  <td className="p-3"><code className="text-[var(--text)] bg-[var(--surface-raised)] px-1 rounded">&quot;env file&quot;</code> matches &quot;load the env file&quot;</td>
                </tr>
                <tr>
                  <td className="p-3 font-bold text-[var(--accent)]">Whole Word</td>
                  <td className="p-3 text-[var(--text-muted)]">Matches only standalone words bounded by spacing or punctuation.</td>
                  <td className="p-3"><code className="text-[var(--text)] bg-[var(--surface-raised)] px-1 rounded">&quot;cat&quot;</code> matches &quot;the cat.&quot; but not &quot;category&quot;</td>
                </tr>
                <tr>
                  <td className="p-3 font-bold text-[var(--accent)]">Substring</td>
                  <td className="p-3 text-[var(--text-muted)]">Simple case-insensitive search matching occurrences inside other words.</td>
                  <td className="p-3"><code className="text-[var(--text)] bg-[var(--surface-raised)] px-1 rounded">&quot;cat&quot;</code> matches both &quot;cat&quot; and &quot;category&quot;</td>
                </tr>
                <tr>
                  <td className="p-3 font-bold text-[var(--accent)]">Fuzzy</td>
                  <td className="p-3 text-[var(--text-muted)]">Typo-tolerant approximate search. Requires query length &gt;= 3.</td>
                  <td className="p-3"><code className="text-[var(--text)] bg-[var(--surface-raised)] px-1 rounded">&quot;javascrit&quot;</code> matches &quot;javascript&quot;</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 3: Downloads */}
        <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-md flex flex-col gap-5">
          <h2 className="text-lg font-bold text-[var(--text)] font-mono flex items-center gap-2.5">
            <Download className="h-5 w-5 text-[var(--warning)]" />
            <span>3. Download Managers</span>
          </h2>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Every utility page displays two distinct download options to match your project integration style:
          </p>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-[var(--border-subtle)] pt-4">
            <div className="p-4 rounded bg-[var(--surface-raised)] border border-[var(--border)] flex flex-col gap-2">
              <h4 className="text-xs font-semibold text-[var(--text)] font-mono">Download script (.py)</h4>
              <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">
                Downloads the single primary executable Python file directly. Perfect if you need a quick system tool with zero extra configuration.
              </p>
            </div>
            <div className="p-4 rounded bg-[var(--surface-raised)] border border-[var(--border)] flex flex-col gap-2">
              <h4 className="text-xs font-semibold text-[var(--text)] font-mono">Download folder (.zip)</h4>
              <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">
                Aggregates all files in the script directory (including readme docs, package dependencies, and testing suites) and compiles them into a ZIP archive.
              </p>
            </div>
          </div>
        </div>

        {/* GitHub link footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between border-t border-[var(--border)] pt-8 gap-4 text-xs">
          <span className="text-[var(--text-dim)] font-mono">PyScripts v0.1.0</span>
          
          <div className="flex items-center gap-4">
            <Link
              href="/search"
              className="flex items-center gap-1 text-[var(--accent)] hover:underline font-mono"
            >
              <span>Try Advanced Search</span>
              <ArrowRight className="h-3 w-3" />
            </Link>
            <span className="text-[var(--border)]">|</span>
            <a
              href="https://github.com/WantedChip/python-scripts"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[var(--text-muted)] hover:text-[var(--text)] transition-colors font-mono"
            >
              <span>View GitHub Repository</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

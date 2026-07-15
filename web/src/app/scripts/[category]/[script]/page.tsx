import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowLeft,
  Github,
  Terminal,
  CheckCircle2,
  AlertCircle,
  Package,
} from "lucide-react";
import scriptsData from "@/data/scripts.json";
import DownloadButtons from "@/components/DownloadButtons";
import FileExplorer from "@/components/FileExplorer";
import TierBadge from "@/components/TierBadge";
import { Script } from "@/lib/search/types";

interface Props {
  params: Promise<{ category: string; script: string }>;
  searchParams: Promise<{ file?: string }>;
}

export async function generateStaticParams() {
  const scripts = scriptsData as Script[];
  return scripts.map((s) => ({
    category: s.category,
    script: s.name,
  }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { script } = await params;
  return {
    title: `${script} — PyScripts`,
    description: `Source code, README, and download utilities for the ${script} Python CLI script.`,
  };
}

export default async function ScriptDetailPage({ params, searchParams }: Props) {
  const { category, script: scriptName } = await params;
  const { file } = await searchParams;
  const scripts = scriptsData as Script[];

  if (!category || !scriptName) notFound();

  const script = scripts.find(
    (s) =>
      s.category.toLowerCase() === category.toLowerCase() &&
      s.name.toLowerCase() === scriptName.toLowerCase()
  );

  if (!script) notFound();

  const hasDependencies = script.requirements.length > 0;

  return (
    <div
      className="flex flex-col bg-[var(--bg)] scripts-detail-page"
      style={{ height: "calc(100vh - var(--header-height, 57px))" }}
    >
      {/* ── Top Info Bar ─────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-[var(--border)] bg-[var(--surface)]">
        {/* Breadcrumb row */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border-subtle)] font-mono text-[11px] text-[var(--text-dim)]">
          <Link
            href={`/browse/${script.category}`}
            className="flex items-center gap-1 hover:text-[var(--text)] transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            <span>browse</span>
          </Link>
          <span>/</span>
          <Link
            href={`/browse/${script.category}`}
            className="capitalize hover:text-[var(--text)] transition-colors"
          >
            {script.category}
          </Link>
          <span>/</span>
          <span className="text-[var(--text)] font-semibold">{script.name}</span>
        </div>

        {/* Script identity + actions row */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-4 px-4 py-3">
          {/* Left: name + description */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <Terminal className="h-5 w-5 text-[var(--accent)] shrink-0 mt-0.5" />
            <div className="flex flex-col gap-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-mono text-base font-bold text-[var(--text)] leading-none">
                  {script.name}
                </h1>
                <TierBadge
                  unranked={script.unranked}
                  coveragePct={script.coveragePct}
                  depCount={script.depCount}
                  size="sm"
                />
                <span className="text-[10px] font-mono border border-[var(--border)] bg-[var(--surface-raised)] px-2 py-0.5 rounded-full text-[var(--text-dim)] uppercase tracking-wider">
                  {script.category}
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)] leading-relaxed line-clamp-1 max-w-2xl">
                {script.description}
              </p>
            </div>
          </div>

          {/* Right: metadata chips + downloads */}
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            {/* Entrypoint chip */}
            <div className="flex items-center gap-1.5 font-mono text-[10px] bg-[var(--surface-raised)] border border-[var(--border)] px-2.5 py-1.5 rounded">
              <Terminal className="h-3 w-3 text-[var(--text-dim)]" />
              <span className="text-[var(--text-muted)]">python</span>
              <span className="text-[var(--accent)] font-semibold">{script.mainFile}</span>
            </div>

            {/* Dependencies chip */}
            {hasDependencies ? (
              <div className="flex items-center gap-1.5 font-mono text-[10px] bg-amber-950/20 border border-[var(--warning)]/30 px-2.5 py-1.5 rounded text-[var(--warning)]">
                <Package className="h-3 w-3" />
                <span>{script.requirements.length} dep{script.requirements.length > 1 ? "s" : ""}</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 font-mono text-[10px] bg-green-950/20 border border-[var(--success)]/30 px-2.5 py-1.5 rounded text-[var(--success)]">
                <CheckCircle2 className="h-3 w-3" />
                <span>stdlib only</span>
              </div>
            )}

            {/* Test chip */}
            {script.hasTests && (
              <div className="flex items-center gap-1.5 font-mono text-[10px] bg-green-950/20 border border-[var(--success)]/30 px-2.5 py-1.5 rounded text-[var(--success)]">
                <CheckCircle2 className="h-3 w-3" />
                <span>tested</span>
              </div>
            )}

            {/* Quality metrics */}
            {!script.unranked && script.pylintScore != null && (
              <div className="hidden sm:flex items-center gap-2 font-mono text-[10px] text-[var(--text-dim)] border border-[var(--border)] bg-[var(--surface-raised)] px-2.5 py-1.5 rounded">
                <span>pylint <span className="text-[var(--text)]">{script.pylintScore.toFixed(1)}</span></span>
                <span className="text-[var(--border)]">·</span>
                <span>cov <span className="text-[var(--text)]">{script.coveragePct}%</span></span>
              </div>
            )}

            {/* GitHub link */}
            <a
              href={`https://github.com/WantedChip/python-scripts/tree/main/${script.path}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 font-mono text-[10px] text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:bg-[var(--surface-hover)] px-2.5 py-1.5 rounded transition-colors"
            >
              <Github className="h-3 w-3" />
              <span>GitHub</span>
            </a>

            {/* Requirements tooltip trigger */}
            {hasDependencies && (
              <details className="relative group">
                <summary className="flex items-center gap-1.5 font-mono text-[10px] cursor-pointer text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:bg-[var(--surface-hover)] px-2.5 py-1.5 rounded transition-colors list-none">
                  <AlertCircle className="h-3 w-3" />
                  <span>deps</span>
                </summary>
                <div className="absolute right-0 top-full mt-1.5 z-30 w-52 bg-[var(--surface-raised)] border border-[var(--border)] p-3 rounded-lg shadow-xl">
                  <p className="font-mono text-[10px] text-[var(--text-dim)] mb-2 uppercase tracking-wider">Requirements</p>
                  <div className="flex flex-wrap gap-1.5">
                    {script.requirements.map((req) => (
                      <span
                        key={req}
                        className="font-mono text-[10px] text-[var(--text)] bg-[var(--surface-hover)] border border-[var(--border)] px-2 py-0.5 rounded"
                      >
                        {req}
                      </span>
                    ))}
                  </div>
                </div>
              </details>
            )}
          </div>
        </div>

        {/* Download strip */}
        <div className="px-4 pb-3">
          <DownloadButtons path={script.path} scriptName={script.name} />
        </div>
      </div>

      {/* ── Full-bleed Code Explorer ──────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        <FileExplorer
          fileTree={script.fileTree}
          scriptPath={script.path}
          scriptName={script.name}
          initialFilePath={file}
        />
      </div>
    </div>
  );
}

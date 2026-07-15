import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Github, Terminal, CheckCircle2, AlertCircle } from "lucide-react";
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
    title: `${script} Script`,
    description: `Details, requirements, and download utilities for the ${script} Python script.`,
  };
}

export default async function ScriptDetailPage({ params, searchParams }: Props) {
  const { category, script: scriptName } = await params;
  const { file } = await searchParams;
  const scripts = scriptsData as Script[];

  if (!category || !scriptName) {
    notFound();
  }

  // Find the exact script
  const script = scripts.find(
    (s) =>
      s.category.toLowerCase() === category.toLowerCase() &&
      s.name.toLowerCase() === scriptName.toLowerCase()
  );

  if (!script) {
    notFound();
  }

  // Parse quality score if present in the readme/manifest (e.g. pylint score or similar)
  // Our build-data reads details. Let's just output script details.
  const hasDependencies = script.requirements.length > 0;

  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-5xl mx-auto flex flex-col gap-8">
        {/* Breadcrumb & Navigation */}
        <div className="flex items-center gap-4">
          <Link
            href={`/browse/${script.category}`}
            className="flex items-center gap-2 font-mono text-xs text-[var(--text-dim)] hover:text-[var(--text)] transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            <span>cd ..</span>
          </Link>
          <span className="text-[var(--border)]">/</span>
          <span className="font-mono text-xs text-[var(--text-dim)]">browse</span>
          <span className="text-[var(--border)]">/</span>
          <Link
            href={`/browse/${script.category}`}
            className="font-mono text-xs text-[var(--text-dim)] hover:text-[var(--text)] capitalize transition-colors"
          >
            {script.category}
          </Link>
          <span className="text-[var(--border)]">/</span>
          <span className="font-mono text-xs text-[var(--text)]">{script.name}</span>
        </div>

        {/* Script Header Info */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border)] pb-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-3xl font-mono font-bold tracking-tight text-[var(--text)] flex items-center gap-2">
              <Terminal className="h-6 w-6 text-[var(--accent)]" />
              <span>{script.name}</span>
            </h1>
            <p className="text-sm text-[var(--text-muted)] max-w-2xl">
              {script.description}
            </p>
          </div>
          <div className="flex items-center gap-2.5 self-start sm:self-center shrink-0">
            <TierBadge
              unranked={script.unranked}
              coveragePct={script.coveragePct}
              depCount={script.depCount}
              size="md"
            />
            <span className="text-xs font-mono border border-[var(--border)] bg-[var(--surface-raised)] px-3 py-1 rounded-full text-[var(--text-muted)] uppercase">
              {script.category}
            </span>
          </div>
        </div>

        {/* Content Split Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main content: File Explorer component */}
          <div className="lg:col-span-2 flex flex-col gap-4">
            <FileExplorer
              fileTree={script.fileTree}
              scriptPath={script.path}
              scriptName={script.name}
              initialFilePath={file}
            />
          </div>

          {/* Sidebar: Download & Requirements Cards */}
          <div className="flex flex-col gap-6 lg:sticky lg:top-8 h-fit">
            {/* Downloads Card */}
            <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg flex flex-col gap-4">
              <h3 className="font-mono text-xs font-semibold text-[var(--text)] uppercase tracking-wider">
                Downloads
              </h3>
              <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                Download the standalone executable Python file or the complete workspace directory containing tests and configurations.
              </p>
              
              <DownloadButtons path={script.path} scriptName={script.name} />
            </div>

            {/* Metadata & Requirements Card */}
            <div className="p-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg flex flex-col gap-4">
              <h3 className="font-mono text-xs font-semibold text-[var(--text)] uppercase tracking-wider">
                Configuration Details
              </h3>

              <div className="flex flex-col gap-3.5">
                {/* Entry File */}
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-[var(--text-dim)] uppercase font-mono">Entrypoint</span>
                  <span className="font-mono text-xs text-[var(--text)] bg-[var(--surface-raised)] border border-[var(--border)] px-2 py-1.5 rounded">
                    python {script.mainFile}
                  </span>
                </div>

                {/* Path */}
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-[var(--text-dim)] uppercase font-mono">Workspace Path</span>
                  <span className="font-mono text-xs text-[var(--text-muted)] bg-[var(--surface-raised)] border border-[var(--border)] px-2 py-1.5 rounded break-all">
                    {script.path}
                  </span>
                </div>

                {/* Requirements */}
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-[var(--text-dim)] uppercase font-mono">Dependencies</span>
                  {hasDependencies ? (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-1 text-[10px] text-[var(--warning)] bg-amber-950/20 border border-[var(--warning)]/20 p-2 rounded">
                        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                        <span>Requires {script.requirements.length} package installs</span>
                      </div>
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
                  ) : (
                    <div className="flex items-center gap-1.5 text-[10px] text-[var(--success)] bg-green-950/20 border border-[var(--success)]/20 p-2 rounded">
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                      <span>Pure Standard Library</span>
                    </div>
                  )}
                </div>

                {/* Test status */}
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-[var(--text-dim)] uppercase font-mono">Testing Suite</span>
                  <div className="flex items-center gap-1.5 text-[10px] text-[var(--success)] bg-green-950/20 border border-[var(--success)]/20 p-2 rounded">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                    <span>Unit tests implemented</span>
                  </div>
                </div>

                {/* GitHub link */}
                <a
                  href={`https://github.com/WantedChip/python-scripts/tree/main/${script.path}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 mt-4 px-4 py-2 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:bg-[var(--surface-hover)] rounded transition-colors"
                >
                  <Github className="h-4 w-4" />
                  <span>View on GitHub</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Play, ShieldAlert, Cpu, ShieldCheck, Code2 } from "lucide-react";
import scriptsData from "@/data/scripts.json";
import { Script } from "@/lib/search/types";
import TierBadge from "@/components/TierBadge";
import StatsStrip from "@/components/StatsStrip";

interface Props {
  params: Promise<{ category: string }>;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  automation: <Cpu className="h-5 w-5 text-[var(--accent)]" />,
  checkers: <ShieldCheck className="h-5 w-5 text-[var(--success)]" />,
  tools: <Code2 className="h-5 w-5 text-[var(--warning)]" />,
};

export async function generateStaticParams() {
  const scripts = scriptsData as Script[];
  const categories = Array.from(new Set(scripts.map((s) => s.category)));
  return categories.map((cat) => ({
    category: cat,
  }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { category } = await params;
  if (!category) {
    return {
      title: "Browse Category",
    };
  }
  const capitalized = category.charAt(0).toUpperCase() + category.slice(1);
  return {
    title: `${capitalized} Scripts`,
    description: `Browse Python CLI scripts inside the ${category} category.`,
  };
}

export default async function CategoryPage({ params }: Props) {
  const { category } = await params;
  const scripts = scriptsData as Script[];

  if (!category) {
    notFound();
  }

  // Filter scripts by category
  const filtered = scripts.filter((s) => s.category.toLowerCase() === category.toLowerCase());

  if (filtered.length === 0) {
    notFound();
  }

  return (
    <div className="bg-[var(--bg)] min-h-full py-16 px-6 sm:px-12 lg:px-24">
      <div className="max-w-5xl mx-auto flex flex-col gap-8">
        {/* Breadcrumb & Back Link */}
        <div className="flex items-center gap-4">
          <Link
            href="/browse"
            className="flex items-center gap-2 font-mono text-xs text-[var(--text-dim)] hover:text-[var(--text)] transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            <span>cd ..</span>
          </Link>
          <span className="text-[var(--border)]">/</span>
          <span className="font-mono text-xs text-[var(--text-dim)]">browse</span>
          <span className="text-[var(--border)]">/</span>
          <span className="font-mono text-xs text-[var(--text)] capitalize">{category}</span>
        </div>

        {/* Header */}
        <div className="flex flex-col gap-2 border-b border-[var(--border)] pb-6">
          <div className="flex items-center gap-2">
            {CATEGORY_ICONS[category.toLowerCase()] || <Code2 className="h-5 w-5" />}
            <h1 className="text-2xl font-bold capitalize text-[var(--text)]">{category}</h1>
          </div>
          <p className="text-xs text-[var(--text-dim)]">
            Showing {filtered.length} {filtered.length === 1 ? "utility" : "utilities"}
          </p>
        </div>

        <StatsStrip />

        {/* Grid List */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {filtered.map((script) => (
            <div
              key={script.name}
              className="flex flex-col justify-between p-5 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--text-dim)] transition-all shadow-md group"
            >
              <div className="flex flex-col gap-3">
                {/* Header info */}
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-mono text-sm font-semibold text-[var(--accent)] group-hover:underline">
                    <Link href={`/scripts/${script.category}/${script.name}`}>
                      {script.name}
                    </Link>
                  </h3>
                  <div className="flex items-center gap-2">
                    <TierBadge
                      unranked={script.unranked}
                      coveragePct={script.coveragePct}
                      depCount={script.depCount}
                    />
                    {script.hasTests && (
                      <span
                        title="Passes unit test suites"
                        className="flex items-center justify-center p-1 rounded bg-green-950/20 border border-[var(--success)]/20 text-[var(--success)]"
                      >
                        <Play className="h-3 w-3 fill-[var(--success)] shrink-0" />
                      </span>
                    )}
                    {script.requirements.length > 0 ? (
                      <span
                        title={`${script.requirements.length} external dependencies`}
                        className="text-[9px] font-mono border border-[var(--warning)]/20 bg-amber-950/20 text-[var(--warning)] px-1.5 py-0.5 rounded"
                      >
                        dep
                      </span>
                    ) : (
                      <span
                        title="Pure standard library"
                        className="text-[9px] font-mono border border-[var(--success)]/20 bg-green-950/20 text-[var(--success)] px-1.5 py-0.5 rounded"
                      >
                        std
                      </span>
                    )}
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs text-[var(--text-muted)] leading-relaxed line-clamp-2">
                  {script.description}
                </p>
              </div>

              {/* Action buttons footer */}
              <div className="flex items-center justify-between border-t border-[var(--border-subtle)] mt-5 pt-4">
                <span className="font-mono text-[10px] text-[var(--text-dim)]">
                  {script.mainFile}
                </span>

                <Link
                  href={`/scripts/${script.category}/${script.name}`}
                  className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--text-dim)] group-hover:text-[var(--text)] transition-colors"
                >
                  <span>Inspect details</span>
                  <ArrowLeft className="h-3 w-3 rotate-180 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

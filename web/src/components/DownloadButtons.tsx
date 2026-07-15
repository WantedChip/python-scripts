"use client";

import React, { useState } from "react";
import { FileCode, Archive, Loader2, AlertCircle } from "lucide-react";

interface DownloadButtonsProps {
  path: string;
  scriptName: string;
}

export default function DownloadButtons({ path, scriptName }: DownloadButtonsProps) {
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownloadZip = async () => {
    if (downloadingZip) return;
    setDownloadingZip(true);
    setError(null);

    try {
      const response = await fetch(`/api/download?path=${encodeURIComponent(path)}&mode=zip`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Failed to compile ZIP archive.");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${scriptName}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      console.error(err);
      const message = err instanceof Error ? err.message : "An error occurred during ZIP creation.";
      setError(message);
    } finally {
      setDownloadingZip(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Download Single File (.py) */}
        <a
          href={`/api/download?path=${encodeURIComponent(path)}&mode=file`}
          download
          className="flex-1 flex items-center justify-center gap-2 px-5 py-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-hover)] transition-all font-medium text-sm focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
        >
          <FileCode className="h-4 w-4 text-[var(--text-muted)]" />
          <span>Download script (.py)</span>
        </a>

        {/* Download ZIP Folder */}
        <button
          onClick={handleDownloadZip}
          disabled={downloadingZip}
          className={`flex-1 flex items-center justify-center gap-2 px-5 py-3 rounded-lg border border-transparent bg-[var(--accent)] text-white hover:bg-[var(--accent-dim)] transition-all font-medium text-sm focus-visible:outline-2 focus-visible:outline-[var(--accent)] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {downloadingZip ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Archive className="h-4 w-4" />
          )}
          <span>{downloadingZip ? "Compiling ZIP..." : "Download folder (.zip)"}</span>
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-[var(--danger)] bg-red-950/20 border border-[var(--danger)]/30 p-3 rounded-lg">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

import { NextRequest, NextResponse } from "next/server";
import { createHighlighter } from "shiki";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let highlighterInstance: any = null;

// Initialize and cache the Shiki highlighter singleton
async function getHighlighter() {
  if (!highlighterInstance) {
    highlighterInstance = await createHighlighter({
      themes: ["github-dark"],
      langs: ["python", "json", "yaml", "markdown", "text", "txt"],
    });
  }
  return highlighterInstance;
}

// Maps file extensions to Shiki language identifiers
function getLanguageFromExtension(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "py":
      return "python";
    case "json":
      return "json";
    case "yaml":
    case "yml":
      return "yaml";
    case "md":
      return "markdown";
    case "txt":
      return "text";
    default:
      return "text";
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filePath = searchParams.get("path");

  if (!filePath) {
    return NextResponse.json(
      { error: "Missing required query parameter: 'path'." },
      { status: 400 }
    );
  }

  try {
    const rawURL = `https://raw.githubusercontent.com/WantedChip/python-scripts/main/${filePath}`;
    
    // Add optional GITHUB_TOKEN if available to avoid rate limits
    const headers: Record<string, string> = {};
    if (process.env.GITHUB_TOKEN) {
      headers["Authorization"] = `Bearer ${process.env.GITHUB_TOKEN}`;
    }

    const response = await fetch(rawURL, {
      headers,
      next: { revalidate: 3600 }, // Cache raw content for 1 hour
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Failed to fetch file content from GitHub: ${response.statusText}` },
        { status: response.status }
      );
    }

    const content = await response.text();
    const lang = getLanguageFromExtension(filePath);

    let highlightedHtml = "";

    // Generate syntax-highlighted HTML server-side using Shiki (except for binary/large files)
    if (content.length < 150000) {
      const highlighter = await getHighlighter();
      highlightedHtml = highlighter.codeToHtml(content, {
        lang,
        theme: "github-dark",
      });
    } else {
      highlightedHtml = `<pre><code>${content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>`;
    }

    return NextResponse.json({
      content,
      highlightedHtml,
      lang,
    });
  } catch (error: unknown) {
    console.error("File content handler error:", error);
    const message = error instanceof Error ? error.message : "An unexpected error occurred reading the file.";
    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}

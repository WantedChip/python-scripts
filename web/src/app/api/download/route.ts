import { NextRequest, NextResponse } from "next/server";
import scriptsData from "@/data/scripts.json";
import JSZip from "jszip";

interface GitHubContentItem {
  name: string;
  path: string;
  download_url: string | null;
  type: "file" | "dir";
}

interface ScriptMetadata {
  name: string;
  category: string;
  path: string;
  description: string;
  mainFile: string;
}

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;

// Helper to set up GitHub API request headers
function getGitHubHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "User-Agent": "python-scripts-webapp",
  };
  if (GITHUB_TOKEN) {
    headers["Authorization"] = `Bearer ${GITHUB_TOKEN}`;
  }
  return headers;
}

/**
 * Recursively fetch all files in a repository directory from GitHub REST API
 * @param path Relative directory path in the repository (e.g. "automation/device-monitor")
 * @param baseFolder Root folder of the script to calculate relative paths inside the ZIP
 */
async function fetchFolderFilesRecursive(
  path: string,
  baseFolder: string
): Promise<{ relativePath: string; buffer: ArrayBuffer }[]> {
  const apiURL = `https://api.github.com/repos/WantedChip/python-scripts/contents/${path}`;
  const response = await fetch(apiURL, {
    headers: getGitHubHeaders(),
    next: { revalidate: 3600 }, // Cache response for 1 hour
  });

  if (!response.ok) {
    if (response.status === 403 || response.status === 429) {
      throw new Error("GitHub API rate limit exceeded. Please configure GITHUB_TOKEN to raise limits.");
    }
    throw new Error(`Failed to read folder contents from GitHub API: ${response.statusText}`);
  }

  const items: GitHubContentItem[] = await response.json();
  const files: { relativePath: string; buffer: ArrayBuffer }[] = [];

  for (const item of items) {
    if (item.type === "file") {
      if (item.download_url) {
        const fileRes = await fetch(item.download_url);
        if (fileRes.ok) {
          const buffer = await fileRes.arrayBuffer();
          // Calculate relative path inside the script directory (e.g. "tests/test_x.py" or "main.py")
          const relativePath = item.path.substring(baseFolder.length + 1);
          files.push({ relativePath, buffer });
        }
      }
    } else if (item.type === "dir") {
      const subFiles = await fetchFolderFilesRecursive(item.path, baseFolder);
      files.push(...subFiles);
    }
  }

  return files;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");
  const mode = searchParams.get("mode");

  if (!path || !mode) {
    return NextResponse.json(
      { error: "Missing required query parameters: 'path' and 'mode'." },
      { status: 400 }
    );
  }

  // Find the script metadata in scripts.json
  const script = (scriptsData as ScriptMetadata[]).find((s) => s.path === path);
  if (!script) {
    return NextResponse.json(
      { error: `Script metadata not found for path: '${path}'.` },
      { status: 404 }
    );
  }

  const { name: scriptName, mainFile } = script;

  try {
    if (mode === "file") {
      // 1. Single File Download Mode
      const rawFileURL = `https://raw.githubusercontent.com/WantedChip/python-scripts/main/${path}/${mainFile}`;
      const response = await fetch(rawFileURL);

      if (!response.ok) {
        return NextResponse.json(
          { error: `Failed to fetch raw script file: ${response.statusText}` },
          { status: response.status }
        );
      }

      const scriptContent = await response.text();

      return new NextResponse(scriptContent, {
        status: 200,
        headers: {
          "Content-Type": "text/x-python; charset=utf-8",
          "Content-Disposition": `attachment; filename="${mainFile}"`,
        },
      });
    } else if (mode === "zip") {
      // 2. Folder ZIP Download Mode
      const files = await fetchFolderFilesRecursive(path, path);

      if (files.length === 0) {
        return NextResponse.json(
          { error: "No files found in the specified script folder." },
          { status: 404 }
        );
      }

      const zip = new JSZip();
      files.forEach((file) => {
        zip.file(file.relativePath, file.buffer);
      });

      const zipBlob = await zip.generateAsync({ type: "blob" });

      return new NextResponse(zipBlob, {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename="${scriptName}.zip"`,
        },
      });
    } else {
      return NextResponse.json(
        { error: `Invalid mode: '${mode}'. Supported modes are 'file' and 'zip'.` },
        { status: 400 }
      );
    }
  } catch (error: any) {
    console.error("Download handler error:", error);
    return NextResponse.json(
      { error: error.message || "An unexpected error occurred during download." },
      { status: 500 }
    );
  }
}

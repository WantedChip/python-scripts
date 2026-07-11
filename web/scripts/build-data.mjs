/**
 * build-data.mjs
 *
 * Pre-build data pipeline. Reads INDEX.md from the repo root (one level up
 * from web/) and each script's README.md + requirements.txt from disk.
 * Produces web/src/data/scripts.json consumed at build time by the site.
 *
 * Run: node scripts/build-data.mjs
 * Automatically called via package.json "prebuild" and "dev" scripts.
 *
 * Design rules (per phase-0-foundation.md §4):
 *  - Never crash the build on bad input; log warnings and continue.
 *  - No GitHub API calls – reads files directly from the monorepo checkout.
 *  - scripts.json holds metadata + README text only; no source code embedded.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { writeFileSync, mkdirSync } from "fs";
import { join, resolve, dirname } from "path";
import { fileURLToPath } from "url";

// ─── Paths ────────────────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(WEB_ROOT, "..");
const INDEX_MD = join(REPO_ROOT, "INDEX.md");
const OUT_DIR = join(WEB_ROOT, "src", "data");
const OUT_FILE = join(OUT_DIR, "scripts.json");

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Read a file safely; return null and log a warning on failure. */
function safeRead(filePath) {
  try {
    return readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

/**
 * Parse the INDEX.md file.
 * Returns an array of { category, name, path, description } objects.
 *
 * INDEX.md structure (per guidelines §6):
 *   ## category-name
 *   | Script | Description |
 *   |---|---|
 *   | [script-name](path/) | description text |
 */
function parseIndexMd(content) {
  const scripts = [];
  let currentCategory = null;

  const lines = content.split(/\r?\n/);

  for (const line of lines) {
    // Detect category header: ## category-name
    const categoryMatch = line.match(/^##\s+(\S+)\s*$/);
    if (categoryMatch) {
      currentCategory = categoryMatch[1];
      continue;
    }

    // Skip non-table lines and the header/separator rows
    if (!line.startsWith("|") || !currentCategory) continue;
    if (line.includes("---")) continue;
    if (/^\|\s*Script\s*\|/i.test(line)) continue;

    // Parse table row: | [name](path/) | description |
    // Use a more permissive split that handles empty cells gracefully
    const cells = line
      .split("|")
      .map((c) => c.trim())
      .filter(Boolean);

    if (cells.length < 2) continue;

    const nameCell = cells[0];
    const description = cells[1];

    if (!nameCell || !description) continue;

    // Extract name + path from markdown link: [name](path/)
    const linkMatch = nameCell.match(/\[([^\]]+)\]\(([^)]+)\)/);
    if (!linkMatch) {
      console.warn(`[build-data] Skipping malformed row in category "${currentCategory}": ${line}`);
      continue;
    }

    const [, name, scriptPath] = linkMatch;
    // Normalise path – strip trailing slash
    const normalised = scriptPath.replace(/\/$/, "");

    scripts.push({
      name,
      category: currentCategory,
      path: normalised,
      description: description.trim(),
    });
  }

  return scripts;
}

/**
 * Find the main .py file for a script folder.
 * Strategy (per phase-0-foundation.md §4.2):
 *  1. File matching the folder name in snake_case directly in the folder.
 *  2. First .py file found directly in the folder (not in tests/ or src/).
 */
function findMainPyFile(scriptAbsPath, name) {
  const snakeName = name.replace(/-/g, "_") + ".py";
  const exact = join(scriptAbsPath, snakeName);
  if (existsSync(exact)) return snakeName;

  // Also check src/<snake_name>/main.py
  const srcMain = join(scriptAbsPath, "src", snakeName.replace(/\.py$/, ""), "main.py");
  if (existsSync(srcMain)) return `src/${snakeName.replace(/\.py$/, "")}/main.py`;

  // Fallback: first .py file directly in the folder
  try {
    const entries = readdirSync(scriptAbsPath, { withFileTypes: true });
    for (const entry of entries) {
      if (
        entry.isFile() &&
        entry.name.endsWith(".py") &&
        entry.name !== "__init__.py"
      ) {
        return entry.name;
      }
    }
  } catch {
    // Directory may not exist
  }

  return null;
}

/**
 * Parse requirements.txt into a list of package name strings.
 * Handles comments, blank lines, and version specifiers.
 */
function parseRequirements(content) {
  if (!content) return [];
  return content
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#") && !l.startsWith("-"))
    .map((l) => l.split(/[=><~!]/)[0].trim())
    .filter(Boolean);
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function main() {
  console.log("[build-data] Reading INDEX.md …");

  const indexContent = safeRead(INDEX_MD);
  if (!indexContent) {
    console.error(`[build-data] ERROR: Could not read ${INDEX_MD}`);
    process.exit(1);
  }

  const rawScripts = parseIndexMd(indexContent);
  console.log(`[build-data] Found ${rawScripts.length} scripts across INDEX.md`);

  const results = [];

  for (const entry of rawScripts) {
    const scriptAbsPath = join(REPO_ROOT, entry.path);

    // README.md
    const readmePath = join(scriptAbsPath, "README.md");
    const readme = safeRead(readmePath);
    if (!readme) {
      console.warn(`[build-data] WARN: No README.md for ${entry.path} — using placeholder`);
    }

    // requirements.txt
    const reqPath = join(scriptAbsPath, "requirements.txt");
    const reqContent = safeRead(reqPath);
    const requirements = parseRequirements(reqContent);

    // tests/ folder
    const hasTests = existsSync(join(scriptAbsPath, "tests"));

    // main .py file
    const mainFile = findMainPyFile(scriptAbsPath, entry.name);

    results.push({
      name: entry.name,
      category: entry.category,
      path: entry.path,
      description: entry.description,
      readme: readme ?? `No README available for ${entry.name}.`,
      requirements,
      hasTests,
      mainFile,
    });
  }

  // Ensure output directory exists
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(OUT_FILE, JSON.stringify(results, null, 2), "utf8");

  console.log(`[build-data] ✓ Wrote ${results.length} scripts to ${OUT_FILE}`);

  // Summary by category
  const categories = [...new Set(results.map((s) => s.category))];
  for (const cat of categories) {
    const count = results.filter((s) => s.category === cat).length;
    console.log(`  ${cat}: ${count} script${count !== 1 ? "s" : ""}`);
  }
}

main();

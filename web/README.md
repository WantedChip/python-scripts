# PyScripts — Web Frontend

Browsable frontend for the [python-scripts](https://github.com/WantedChip/python-scripts)
monorepo. Built with Next.js 15 (App Router) and Tailwind CSS v4.

---

## Running locally

```bash
cd web
npm install --ignore-scripts --legacy-peer-deps
npm run dev
```

> **Note:** The `--ignore-scripts` flag is required on this machine because
> `unrs-resolver`'s postinstall script attempts to resolve a Windows symlink
> (`C:\Users\Lenovo\Downloads`) that doesn't exist. The flag skips all
> postinstall scripts; packages work normally at runtime.

`npm run dev` runs `build-data.mjs` first (see Data Pipeline below), then
starts the Next.js dev server at http://localhost:3000.

---

## Data pipeline

`scripts/build-data.mjs` — a plain Node.js script that:

1. Reads `../INDEX.md` (one level up — the repo root)
2. Parses every category and script table row
3. For each script: reads its `README.md`, `requirements.txt`, detects a
   `tests/` folder, and finds the main `.py` file
4. Writes everything to `src/data/scripts.json`

The pipeline runs automatically on every build (`prebuild` hook) and dev
start. `scripts.json` is gitignored — it's always regenerated, never
hand-edited.

**Graceful failures:** a script with no `README.md` gets a placeholder; a
malformed INDEX.md row is skipped with a warning. The build never crashes on
bad input.

**Windows junction note:** `npm run dev` and `npm run build` use
`node --preserve-symlinks-main` to avoid Node.js failing on the workspace
junction (`C:\Users\Dev2\Documents\workspace` → `C:\Users\Lenovo\Downloads\…`).

---

## Design tokens

All design decisions are documented here so later phases don't re-discover
them by reading `globals.css`.

### Fonts

Loaded via `next/font/google` in `src/app/layout.tsx`:

| Variable | Font | Usage |
|---|---|---|
| `--font-geist-sans` / `--font-sans` | Geist Sans | UI prose, body text |
| `--font-geist-mono` / `--font-mono` | Geist Mono | Script names, paths, buttons, code |

### Color palette (CSS custom properties in `src/app/globals.css`)

| Variable | Value | Role |
|---|---|---|
| `--accent` | `#7c3aed` | Primary accent (violet-600) |
| `--accent-dim` | `#5b21b6` | Hover/active accent state |
| `--accent-glow` | `rgba(124,58,237,0.2)` | Accent shadow / glow |
| `--accent-subtle` | `rgba(124,58,237,0.08)` | Accent background tint |
| `--bg` | `#09090b` | Page background (zinc-950) |
| `--surface` | `#18181b` | Card/panel background (zinc-900) |
| `--surface-raised` | `#1f1f23` | Slightly elevated surface |
| `--surface-hover` | `#27272a` | Hover state for surface (zinc-800) |
| `--border` | `#27272a` | Standard border (zinc-800) |
| `--border-subtle` | `#1f1f23` | Subtle border |
| `--text` | `#fafafa` | Primary text (zinc-50) |
| `--text-muted` | `#a1a1aa` | Secondary text (zinc-400) |
| `--text-dim` | `#71717a` | Tertiary/placeholder text (zinc-500) |
| `--success` | `#22c55e` | Success state |
| `--warning` | `#f59e0b` | Warning state |
| `--danger` | `#ef4444` | Error/danger state |

### Design principles

- **Dark-first** — no light mode; terminal/developer-tool aesthetic
- **Flat and confident** — no glassmorphism, no `rounded-3xl` everywhere
- **Mono everywhere code-adjacent** — script names, paths, buttons, slugs
  all use `--font-mono`
- **Accent used sparingly** — one real accent color (`--accent`), not
  scattered highlight colors

---

## Project structure

```
web/
├── scripts/
│   └── build-data.mjs      # Data pipeline (pre-build)
├── src/
│   ├── app/
│   │   ├── layout.tsx       # Root layout (fonts, Header, Footer)
│   │   ├── page.tsx         # Home page
│   │   ├── globals.css      # Design tokens + base styles
│   │   └── browse/
│   │       └── page.tsx     # Browse placeholder (Phase 1 feature)
│   ├── components/
│   │   ├── Header.tsx
│   │   └── Footer.tsx
│   └── data/
│       └── scripts.json     # GENERATED — gitignored, do not edit
├── public/
├── package.json
├── tsconfig.json
├── next.config.ts
└── README.md               # this file
```

---

## Phases

| Phase | Status | Scope |
|---|---|---|
| **0 — Foundation** | ✅ Done | Scaffold, data pipeline, home page, design system |
| **1 — Browse & Search** | 🔜 Planned | Category pages, script cards, Fuse.js search |
| **2 — Script Detail** | 🔜 Planned | Per-script pages, code viewer (Shiki), download |
| **3 — Polish** | 🔜 Planned | Command palette, animations, SEO |

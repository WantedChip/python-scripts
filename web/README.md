# PyScripts Web App

[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=nextjs)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-blue?style=flat-square&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?style=flat-square&logo=typescript)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38bdf8?style=flat-square&logo=tailwindcss)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

A modern, terminal-styled catalog site for browsing, searching, and inspecting CLI utilities in the **python-scripts** repository.

---

## Features

- **Category Browser**: Navigate through curated categories like `automation`, `checkers`, and `tools`.
- **Advanced Search Engine**: Multi-mode search options (Broad, Strict, Fuzzy, Substring, and Whole Word matching) with highlighted search span offsets.
- **Interactive Code Explorer**: VS Code-style workspace viewer powered by **Shiki** syntax highlights to inspect script files, readmes, and test cases directly in the browser.
- **Global Command Palette**: Terminal-style popover console (`⌘K` / `Ctrl+K`) for jumping to scripts/files, clipboard command copy, and downloads.
- **Dynamic Quality Badges**: Automated calculation of quality tiers (S to D) using pylint metrics, test coverage percentages, and dependency footprints.

---

## How It Works

1. **Build Data Pipeline**: Before compiling, `scripts/build-data.mjs` parses the repository root `INDEX.md` and script details (such as README files, requirements, test flags, and recursive folder contents). It generates a lightweight index inside `src/data/scripts.json` without embedding actual source code.
2. **On-Demand Content Fetching**: When inspecting source files in the Code Explorer, the website queries a serverless API proxy endpoint `/api/file-content` which fetches raw script content directly from the GitHub repository and runs Shiki highlights server-side.
3. **Optimized Build**: Next.js pre-renders all category catalogs and documentations statically at build time, ensuring fast load times and optimized client bundles.

---

## Running Locally

1. Install dependencies:
   ```bash
   cd web
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000) to view the application.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

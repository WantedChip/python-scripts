# EPUB Doctor

Comprehensive diagnostic tool for inspecting EPUB ebook structures, broken links, missing metadata, oversized images, duplicate chapters, and internal XML schema errors.

## Features
- **Container & OPF Parsing**: Validates `container.xml`, locates `content.opf`, parses metadata, manifest, and spine items.
- **TOC & Link Validation**: Checks `toc.ncx` / `nav.xhtml` navigation links, internal HTML `<a href="...">` links, and fragment `#anchor` IDs.
- **XML Syntax Verification**: Validates XML integrity across XHTML chapters, OPF manifests, SVG graphics, and NCX files.
- **Asset Inspection**: Flag oversized image assets (`.png`, `.jpeg`, `.svg`, `.webp`) exceeding customizable threshold.
- **Structure Diagnostics**: Detects missing metadata (title, author, language, identifier), orphaned assets, and duplicate spine items.

## Usage

### Diagnose an EPUB file
```bash
python main.py book.epub
```

### Specify max image size threshold (in KB)
```bash
python main.py book.epub --max-img-size-kb 1000
```

### Generate JSON diagnostic report
```bash
python main.py book.epub --json --output report.json
```

"""EPUB Doctor Diagnostic Tool.

Inspects EPUB files (ZIP archives) for structural integrity, broken internal links,
missing metadata, oversized image assets, invalid XML, and duplicate/orphaned content.
"""

# pylint: disable=too-many-instance-attributes,too-many-branches
# pylint: disable=too-many-statements,too-many-locals,too-few-public-methods
# pylint: disable=missing-class-docstring,missing-function-docstring,consider-using-with

import argparse
import html.parser
import json
import posixpath
import sys
import urllib.parse
import xml.etree.ElementTree as ET  # nosec B405
import zipfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    location: Optional[str] = None


class HTMLAnchorExtractor(html.parser.HTMLParser):
    """HTML parser to extract element IDs, anchor names, and outgoing hrefs/srcs."""

    def __init__(self) -> None:
        super().__init__()
        self.defined_ids: Set[str] = set()
        self.outgoing_links: List[Tuple[str, str]] = []  # (tag_name, ref)

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}

        # Collect defined IDs and anchor names
        if "id" in attr_dict:
            self.defined_ids.add(attr_dict["id"])
        if tag == "a" and "name" in attr_dict:
            self.defined_ids.add(attr_dict["name"])

        # Collect outgoing links
        for link_attr in ("href", "src"):
            if link_attr in attr_dict:
                ref = attr_dict[link_attr]
                # Filter out external http/https/mailto URLs
                if not urllib.parse.urlparse(ref).scheme:
                    self.outgoing_links.append((tag, ref))


class EpubDoctor:
    """Inspector engine for EPUB zip files."""

    def __init__(self, epub_path: Path, max_img_size_kb: float = 2000.0):
        self.epub_path = epub_path
        self.max_img_size_bytes = max_img_size_kb * 1024
        self.issues: List[Issue] = []
        self.zip_file: Optional[zipfile.ZipFile] = None

        self.opf_path: Optional[str] = None
        self.manifest: Dict[str, Dict[str, str]] = {}  # id -> {href, media-type}
        self.spine: List[str] = []  # list of idrefs
        self.toc_path: Optional[str] = None
        self.file_ids: Dict[str, Set[str]] = {}  # zip_path -> set of defined html IDs

    def run_diagnostics(self) -> Dict[str, Any]:
        """Execute complete diagnostic suite on EPUB file."""
        if not self.epub_path.exists():
            self._add_issue(
                Severity.CRITICAL,
                "FILE_NOT_FOUND",
                f"File '{self.epub_path}' does not exist.",
            )
            return self._build_report()

        try:
            self.zip_file = zipfile.ZipFile(self.epub_path, "r")
        except zipfile.BadZipFile:
            self._add_issue(
                Severity.CRITICAL,
                "BAD_ZIP_FILE",
                "Target file is not a valid ZIP archive.",
            )
            return self._build_report()
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._add_issue(
                Severity.CRITICAL,
                "CANNOT_OPEN_ZIP",
                f"Failed to open archive: {e}",
            )
            return self._build_report()

        try:
            self._check_mimetype()
            self._parse_container()
            if self.opf_path:
                self._parse_opf()
                self._validate_xml_files()
                self._validate_links_and_anchors()
                self._check_oversized_assets()
                self._check_duplicates_and_orphans()
        finally:
            if self.zip_file:
                self.zip_file.close()

        return self._build_report()

    def _add_issue(
        self,
        severity: Severity,
        code: str,
        message: str,
        location: Optional[str] = None,
    ) -> None:
        self.issues.append(
            Issue(
                severity=severity,
                code=code,
                message=message,
                location=location,
            )
        )

    def _check_mimetype(self) -> None:
        assert self.zip_file is not None  # nosec B101
        namelist = self.zip_file.namelist()
        if "mimetype" not in namelist:
            self._add_issue(
                Severity.WARNING,
                "MISSING_MIMETYPE",
                "Archive is missing required 'mimetype' file.",
            )
        else:
            raw = self.zip_file.read("mimetype")
            content = raw.decode("utf-8", errors="ignore").strip()
            if content != "application/epub+zip":
                self._add_issue(
                    Severity.WARNING,
                    "INVALID_MIMETYPE",
                    (
                        f"Unexpected mimetype content '{content}', expected "
                        "'application/epub+zip'."
                    ),
                    location="mimetype",
                )

    def _parse_container(self) -> None:
        assert self.zip_file is not None  # nosec B101
        container_path = "META-INF/container.xml"
        if container_path not in self.zip_file.namelist():
            self._add_issue(
                Severity.CRITICAL,
                "MISSING_CONTAINER_XML",
                f"Missing required file '{container_path}'.",
            )
            return

        try:
            tree = ET.fromstring(self.zip_file.read(container_path))  # nosec B314
            # Handle XML namespace
            rootfiles = tree.findall(".//{*}rootfile")
            if not rootfiles:
                self._add_issue(
                    Severity.CRITICAL,
                    "NO_ROOTFILE",
                    "No <rootfile> entries found in container.xml.",
                )
                return

            self.opf_path = rootfiles[0].attrib.get("full-path")
            if not self.opf_path or self.opf_path not in self.zip_file.namelist():
                self._add_issue(
                    Severity.CRITICAL,
                    "OPF_NOT_FOUND",
                    (
                        f"OPF file '{self.opf_path}' specified in container.xml "
                        "does not exist."
                    ),
                    location=container_path,
                )
                self.opf_path = None
        except ET.ParseError as pe:
            self._add_issue(
                Severity.CRITICAL,
                "INVALID_CONTAINER_XML",
                f"XML parse error in container.xml: {pe}",
                location=container_path,
            )

    def _parse_opf(self) -> None:
        assert self.zip_file is not None  # nosec B101
        assert self.opf_path is not None  # nosec B101
        try:
            data = self.zip_file.read(self.opf_path)
            root = ET.fromstring(data)  # nosec B314
        except ET.ParseError as pe:
            self._add_issue(
                Severity.CRITICAL,
                "INVALID_OPF_XML",
                f"XML parse error in OPF file: {pe}",
                location=self.opf_path,
            )
            return

        # 1. Metadata check
        metadata = root.find("{*}metadata")
        if metadata is None:
            self._add_issue(
                Severity.ERROR,
                "MISSING_METADATA",
                "OPF missing <metadata> element.",
                location=self.opf_path,
            )
        else:
            required_meta = ["title", "language", "identifier"]
            found_meta = {elem.tag.split("}")[-1].lower() for elem in metadata}
            for req in required_meta:
                if req not in found_meta:
                    self._add_issue(
                        Severity.ERROR,
                        "MISSING_REQUIRED_METADATA",
                        f"Missing required Dublin Core metadata element: dc:{req}.",
                        location=self.opf_path,
                    )
            if "creator" not in found_meta:
                self._add_issue(
                    Severity.WARNING,
                    "MISSING_CREATOR",
                    "Missing recommended Dublin Core metadata element: dc:creator.",
                    location=self.opf_path,
                )

        # 2. Manifest check
        manifest_elem = root.find("{*}manifest")
        if manifest_elem is None:
            self._add_issue(
                Severity.CRITICAL,
                "MISSING_MANIFEST",
                "OPF missing <manifest> element.",
                location=self.opf_path,
            )
            return

        opf_dir = posixpath.dirname(self.opf_path)
        for item in manifest_elem.findall("{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type", "")

            if not item_id or not href:
                self._add_issue(
                    Severity.ERROR,
                    "INVALID_MANIFEST_ITEM",
                    "Manifest item missing id or href attribute.",
                    location=self.opf_path,
                )
                continue

            if opf_dir:
                full_href = posixpath.normpath(posixpath.join(opf_dir, href))
            else:
                full_href = posixpath.normpath(href)

            self.manifest[item_id] = {
                "href": full_href,
                "media_type": media_type,
                "raw_href": href,
            }

            if full_href not in self.zip_file.namelist():
                self._add_issue(
                    Severity.ERROR,
                    "MISSING_MANIFEST_FILE",
                    f"Manifest item '{item_id}' references missing file '{full_href}'.",
                    location=self.opf_path,
                )

            if media_type == "application/x-dtbncx+xml" or "ncx" in item_id.lower():
                self.toc_path = full_href

        # 3. Spine check
        spine_elem = root.find("{*}spine")
        if spine_elem is None:
            self._add_issue(
                Severity.CRITICAL,
                "MISSING_SPINE",
                "OPF missing <spine> element.",
                location=self.opf_path,
            )
            return

        toc_attr = spine_elem.attrib.get("toc")
        if toc_attr and toc_attr in self.manifest:
            self.toc_path = self.manifest[toc_attr]["href"]

        seen_spine_ids = set()
        for itemref in spine_elem.findall("{*}itemref"):
            idref = itemref.attrib.get("idref")
            if not idref:
                continue
            if idref not in self.manifest:
                self._add_issue(
                    Severity.ERROR,
                    "SPINE_IDREF_NOT_IN_MANIFEST",
                    f"Spine itemref '{idref}' not found in manifest.",
                    location=self.opf_path,
                )
            if idref in seen_spine_ids:
                self._add_issue(
                    Severity.WARNING,
                    "DUPLICATE_SPINE_ITEM",
                    f"Spine contains duplicate entry for itemref '{idref}'.",
                    location=self.opf_path,
                )
            seen_spine_ids.add(idref)
            self.spine.append(idref)

    def _validate_xml_files(self) -> None:
        """Parse XML/XHTML files in ZIP to check syntax errors."""
        assert self.zip_file is not None  # nosec B101
        xml_exts = (".xhtml", ".xml", ".svg")
        xml_types = (
            "application/xhtml+xml",
            "application/xml",
            "image/svg+xml",
        )
        for item in self.manifest.values():
            href = item["href"]
            media_type = item["media_type"]

            if href not in self.zip_file.namelist():
                continue

            if media_type in xml_types or href.endswith(xml_exts):
                try:
                    content = self.zip_file.read(href)
                    ET.fromstring(content)  # nosec B314
                except ET.ParseError as pe:
                    self._add_issue(
                        Severity.ERROR,
                        "XML_SYNTAX_ERROR",
                        f"XML parse failure: {pe}",
                        location=href,
                    )
                except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
                    pass

    def _validate_links_and_anchors(self) -> None:
        """Extract all HTML anchors and validate outgoing href/src targets."""
        assert self.zip_file is not None  # nosec B101
        html_exts = (".xhtml", ".html")
        html_types = ("application/xhtml+xml", "text/html")
        html_files = [
            item["href"]
            for item in self.manifest.values()
            if item["href"] in self.zip_file.namelist()
            and (item["media_type"] in html_types or item["href"].endswith(html_exts))
        ]

        extracted_links: Dict[str, List[Tuple[str, str]]] = {}

        # Pass 1: Parse all HTML files for defined IDs and outgoing links
        for href in html_files:
            try:
                raw_html = self.zip_file.read(href)
                content = raw_html.decode("utf-8", errors="replace")
                parser = HTMLAnchorExtractor()
                parser.feed(content)
                self.file_ids[href] = parser.defined_ids
                extracted_links[href] = parser.outgoing_links
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._add_issue(
                    Severity.WARNING,
                    "HTML_PARSING_FAILED",
                    f"Failed to parse HTML structure: {e}",
                    location=href,
                )

        # Pass 2: Verify outgoing links and fragment anchors
        namelist = set(self.zip_file.namelist())
        for src_file, links in extracted_links.items():
            src_dir = posixpath.dirname(src_file)

            for tag, ref in links:
                parsed = urllib.parse.urlparse(ref)
                path_part = parsed.path
                fragment = parsed.fragment

                if path_part:
                    target_file = posixpath.normpath(posixpath.join(src_dir, path_part))
                else:
                    target_file = src_file

                if target_file not in namelist:
                    self._add_issue(
                        Severity.ERROR,
                        "BROKEN_INTERNAL_LINK",
                        (
                            f"Tag <{tag}> references missing target file "
                            f"'{path_part}' (resolved: '{target_file}')."
                        ),
                        location=src_file,
                    )
                elif fragment:
                    # Validate anchor fragment
                    target_ids = self.file_ids.get(target_file, set())
                    if fragment not in target_ids:
                        self._add_issue(
                            Severity.ERROR,
                            "BROKEN_ANCHOR_FRAGMENT",
                            (
                                f"Link references missing anchor ID '#{fragment}' "
                                f"in file '{target_file}'."
                            ),
                            location=src_file,
                        )

    def _check_oversized_assets(self) -> None:
        """Flag image assets exceeding size threshold."""
        assert self.zip_file is not None  # nosec B101
        img_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
        for item in self.manifest.values():
            href = item["href"]
            media_type = item["media_type"]

            if href not in self.zip_file.namelist():
                continue

            is_image = media_type.startswith("image/") or href.lower().endswith(
                img_exts
            )
            if is_image:
                info = self.zip_file.getinfo(href)
                if info.file_size > self.max_img_size_bytes:
                    size_kb = info.file_size / 1024.0
                    max_kb = self.max_img_size_bytes / 1024.0
                    self._add_issue(
                        Severity.WARNING,
                        "OVERSIZED_IMAGE",
                        (
                            f"Image asset size ({size_kb:.1f} KB) exceeds limit "
                            f"({max_kb:.1f} KB)."
                        ),
                        location=href,
                    )

    def _check_duplicates_and_orphans(self) -> None:
        """Identify orphaned files inside ZIP not listed in OPF manifest."""
        assert self.zip_file is not None  # nosec B101
        manifest_files = {item["href"] for item in self.manifest.values()}
        if self.opf_path:
            manifest_files.add(self.opf_path)
        manifest_files.add("META-INF/container.xml")
        manifest_files.add("mimetype")

        for file_in_zip in self.zip_file.namelist():
            if file_in_zip.endswith("/") or file_in_zip.startswith("META-INF/"):
                continue
            if file_in_zip not in manifest_files:
                self._add_issue(
                    Severity.WARNING,
                    "ORPHANED_FILE",
                    f"File '{file_in_zip}' present in archive but not in OPF manifest.",
                    location=file_in_zip,
                )

    def _build_report(self) -> Dict[str, Any]:
        counts = {sev.value: 0 for sev in Severity}
        for issue in self.issues:
            counts[issue.severity.value] += 1

        crit_err_sum = counts[Severity.CRITICAL.value] + counts[Severity.ERROR.value]
        status_str = "FAIL" if crit_err_sum > 0 else "PASS"

        return {
            "epub_path": str(self.epub_path),
            "status": status_str,
            "summary": counts,
            "issues": [asdict(issue) for issue in self.issues],
        }


def format_text_report(report: Dict[str, Any]) -> str:
    crit_c = report["summary"]["CRITICAL"]
    err_c = report["summary"]["ERROR"]
    warn_c = report["summary"]["WARNING"]

    line2 = (
        f" Status: {report['status']} | Critical: {crit_c} | Errors: {err_c} | "
        f"Warnings: {warn_c}"
    )
    lines = [
        "=" * 60,
        f" EPUB DOCTOR DIAGNOSTIC REPORT: {report['epub_path']}",
        line2,
        "=" * 60,
        "",
    ]

    if not report["issues"]:
        lines.append("No structural errors or warnings detected.")
    else:
        for idx, issue in enumerate(report["issues"], 1):
            sev = issue["severity"]
            code = issue["code"]
            msg = issue["message"]
            loc = f" [{issue['location']}]" if issue["location"] else ""
            lines.append(f"#{idx} [{sev}] {code}{loc}")
            lines.append(f"   {msg}")
            lines.append("-" * 60)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect and diagnose EPUB files.")
    parser.add_argument("epub", type=str, help="Path to .epub file.")
    parser.add_argument(
        "--max-img-size-kb",
        type=float,
        default=2000.0,
        help="Maximum allowed image size in KB (default: 2000 KB).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostic report in JSON format.",
    )
    parser.add_argument(
        "--output", type=str, help="Save report to specified output file."
    )

    args = parser.parse_args()

    doctor = EpubDoctor(Path(args.epub), max_img_size_kb=args.max_img_size_kb)
    report = doctor.run_diagnostics()

    if args.json:
        out_str = json.dumps(report, indent=2)
    else:
        out_str = format_text_report(report)

    if args.output:
        Path(args.output).write_text(out_str, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(out_str)

    if report["status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()

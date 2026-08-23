"""Unit tests for epub-doctor tool."""

import contextlib
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import main as main_module
from main import EpubDoctor, format_text_report

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

VALID_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:language>{lang}</dc:language>
    <dc:identifier>{ident}</dc:identifier>
    {creator}
  </metadata>
  <manifest>{items}</manifest>
  <spine>{refs}</spine>
</package>"""


def make_epub(files_dict: dict) -> bytes:
    """Helper to generate in-memory EPUB zip file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for filename, content in files_dict.items():
            if isinstance(content, str):
                z.writestr(filename, content.encode("utf-8"))
            else:
                z.writestr(filename, content)
    return buf.getvalue()


def create_test_epub_zip(files_dict: dict) -> bytes:
    """Helper to generate in-memory EPUB zip file."""
    return make_epub(files_dict)


def build_opf(
    items: str = '<item id="ch1" href="ch1.xhtml"'
    ' media-type="application/xhtml+xml"/>',
    refs: str = '<itemref idref="ch1"/>',
) -> str:
    """Render a minimal valid OPF package document."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>T</dc:title><dc:language>en</dc:language>"
        "<dc:identifier>i</dc:identifier><dc:creator>A</dc:creator>"
        "</metadata>"
        f"<manifest>{items}</manifest>"
        f"<spine>{refs}</spine>"
        "</package>"
    )


def _good_files() -> dict:
    """Build the file set of a minimal well-formed EPUB."""
    return {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": CONTAINER_XML.format(opf="content.opf"),
        "content.opf": build_opf(),
        "ch1.xhtml": '<html><body><h1 id="sec1">Chapter One</h1></body></html>',
    }


def write_epub(tmpdir: str, name: str, files_dict: dict) -> Path:
    """Write an in-memory EPUB into ``tmpdir`` and return its path."""
    epub_file = Path(tmpdir) / name
    epub_file.write_bytes(make_epub(files_dict))
    return epub_file


def run_doctor(epub_path: Path) -> dict:
    """Run full diagnostics on ``epub_path`` and return the report."""
    return EpubDoctor(epub_path).run_diagnostics()


class TestEpubDoctor(unittest.TestCase):
    """Test cases for EPUB structure validation."""

    def test_valid_epub(self) -> None:
        files = {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            "OEBPS/content.opf": """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">urn:uuid:12345</dc:identifier>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>""",
            "OEBPS/ch1.xhtml": """<html xmlns="http://www.w3.org/1999/xhtml">
<body>
  <h1 id="sec1">Chapter 1</h1>
  <a href="ch2.xhtml#sec2">Go to Ch 2</a>
</body>
</html>""",
            "OEBPS/ch2.xhtml": """<html xmlns="http://www.w3.org/1999/xhtml">
<body>
  <h1 id="sec2">Chapter 2</h1>
</body>
</html>""",
        }

        with TemporaryDirectory() as tmpdir:
            epub_file = Path(tmpdir) / "test.epub"
            epub_file.write_bytes(create_test_epub_zip(files))

            doctor = EpubDoctor(epub_file)
            report = doctor.run_diagnostics()

            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["summary"]["CRITICAL"], 0)
            self.assertEqual(report["summary"]["ERROR"], 0)

    def test_missing_container(self) -> None:
        files = {"mimetype": "application/epub+zip"}
        with TemporaryDirectory() as tmpdir:
            epub_file = Path(tmpdir) / "bad.epub"
            epub_file.write_bytes(create_test_epub_zip(files))

            doctor = EpubDoctor(epub_file)
            report = doctor.run_diagnostics()

            self.assertEqual(report["status"], "FAIL")
            issues = report["issues"]
            self.assertTrue(any(i["code"] == "MISSING_CONTAINER_XML" for i in issues))

    def test_broken_link_and_missing_anchor(self) -> None:
        c_xml = (
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument'
            ':xmlns:container"><rootfiles><rootfile full-path="content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles>'
            "</container>"
        )
        opf_xml = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>'
            "Test</dc:title><dc:language>en</dc:language><dc:identifier>123"
            '</dc:identifier></metadata><manifest><item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/><item id="ch2" href="ch2.xhtml"'
            ' media-type="application/xhtml+xml"/></manifest><spine>'
            '<itemref idref="ch1"/><itemref idref="ch2"/></spine></package>'
        )
        ch2_xml = '<html><body><h1 id="real_anchor">Ch 2</h1></body></html>'
        files = {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": c_xml,
            "content.opf": opf_xml,
            "ch1.xhtml": (
                '<html><body><a href="missing.xhtml">Broken</a>'
                '<a href="ch2.xhtml#nonexistent">Broken Anchor</a></body></html>'
            ),
            "ch2.xhtml": ch2_xml,
        }

        with TemporaryDirectory() as tmpdir:
            epub_file = Path(tmpdir) / "links.epub"
            epub_file.write_bytes(create_test_epub_zip(files))

            doctor = EpubDoctor(epub_file)
            report = doctor.run_diagnostics()

            self.assertEqual(report["status"], "FAIL")
            codes = [i["code"] for i in report["issues"]]
            self.assertIn("BROKEN_INTERNAL_LINK", codes)
            self.assertIn("BROKEN_ANCHOR_FRAGMENT", codes)

    def test_oversized_image_detection(self) -> None:
        # Create dummy image content larger than 10KB threshold for test
        large_image_data = b"0" * (15 * 1024)

        c_xml = (
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument'
            ':xmlns:container"><rootfiles><rootfile full-path="content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles>'
            "</container>"
        )
        opf_xml = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>'
            "Test</dc:title><dc:language>en</dc:language><dc:identifier>123"
            '</dc:identifier></metadata><manifest><item id="img1" href="big.png"'
            ' media-type="image/png"/></manifest><spine></spine></package>'
        )
        files = {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": c_xml,
            "content.opf": opf_xml,
            "big.png": large_image_data,
        }

        with TemporaryDirectory() as tmpdir:
            epub_file = Path(tmpdir) / "image.epub"
            epub_file.write_bytes(create_test_epub_zip(files))

            doctor = EpubDoctor(epub_file, max_img_size_kb=10.0)
            report = doctor.run_diagnostics()

            codes = [i["code"] for i in report["issues"]]
            self.assertIn("OVERSIZED_IMAGE", codes)


class TestEpubCriticalPaths(unittest.TestCase):
    """Tests for top-level failure modes: missing file, bad zip."""

    def test_missing_file_reports_file_not_found(self) -> None:
        """A non-existent path yields a CRITICAL FILE_NOT_FOUND issue."""
        doctor = EpubDoctor(Path("Z:/definitely/missing.epub"))
        report = doctor.run_diagnostics()
        self.assertEqual(report["status"], "FAIL")
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("FILE_NOT_FOUND", codes)

    def test_corrupt_zip_reports_bad_zip(self) -> None:
        """Non-zip content is reported as BAD_ZIP_FILE."""
        with TemporaryDirectory() as tmpdir:
            epub_file = Path(tmpdir) / "corrupt.epub"
            epub_file.write_bytes(b"this is not a zip archive at all")
            report = EpubDoctor(epub_file).run_diagnostics()
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("BAD_ZIP_FILE", codes)

    def test_unopenable_zip_reports_cannot_open(self) -> None:
        """Unexpected open failures are caught as CANNOT_OPEN_ZIP."""
        with TemporaryDirectory() as tmpdir:
            epub_file = write_epub(tmpdir, "ok.epub", _good_files())
            with mock.patch.object(
                main_module.zipfile, "ZipFile", side_effect=ValueError("boom")
            ):
                report = EpubDoctor(epub_file).run_diagnostics()
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("CANNOT_OPEN_ZIP", codes)


class TestMimetypeChecks(unittest.TestCase):
    """Tests for mimetype presence and content validation."""

    def test_missing_mimetype_flagged(self) -> None:
        """Archives without a mimetype entry raise a WARNING."""
        files = _good_files()
        del files["mimetype"]
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "nomime.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("MISSING_MIMETYPE", codes)

    def test_invalid_mimetype_content_flagged(self) -> None:
        """A wrong mimetype payload raises INVALID_MIMETYPE."""
        files = _good_files()
        files["mimetype"] = "application/zip"
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "badmime.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("INVALID_MIMETYPE", codes)
        locations = [i["location"] for i in report["issues"]]
        self.assertIn("mimetype", locations)


class TestContainerParsing(unittest.TestCase):
    """Tests for META-INF/container.xml parsing."""

    def test_no_rootfile_entries_flagged(self) -> None:
        """container.xml without rootfile entries is CRITICAL."""
        files = _good_files()
        files["META-INF/container.xml"] = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument'
            ':xmlns:container"><rootfiles></rootfiles></container>'
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "norf.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("NO_ROOTFILE", codes)

    def test_rootfile_target_missing_flagged(self) -> None:
        """A rootfile pointing outside the archive yields OPF_NOT_FOUND."""
        files = _good_files()
        del files["content.opf"]
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "noopf.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("OPF_NOT_FOUND", codes)

    def test_malformed_container_xml_flagged(self) -> None:
        """Unparseable container XML yields INVALID_CONTAINER_XML."""
        files = _good_files()
        files["META-INF/container.xml"] = "<container><rootfiles>"
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "badcont.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("INVALID_CONTAINER_XML", codes)


class TestOpfParsing(unittest.TestCase):
    """Tests for OPF package document parsing."""

    def test_malformed_opf_xml_flagged(self) -> None:
        """Unparseable OPF XML yields INVALID_OPF_XML."""
        files = _good_files()
        files["content.opf"] = "<package><metadata>"
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "badopf.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("INVALID_OPF_XML", codes)

    def test_package_missing_metadata_manifest_spine(self) -> None:
        """An empty package reports metadata/manifest but stops before spine."""
        files = _good_files()
        files["content.opf"] = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"/>'
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "empty.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("MISSING_METADATA", codes)
        self.assertIn("MISSING_MANIFEST", codes)
        self.assertNotIn("MISSING_SPINE", codes)

    def test_incomplete_metadata_flags(self) -> None:
        """Metadata lacking dc elements raises per-element issues."""
        files = _good_files()
        files["content.opf"] = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>Only Title</dc:title></metadata>"
            '<manifest><item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch1"/></spine>'
            "</package>"
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "meta.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertEqual(codes.count("MISSING_REQUIRED_METADATA"), 2)
        self.assertIn("MISSING_CREATOR", codes)

    def test_manifest_without_spine_flagged(self) -> None:
        """A package manifest without a spine yields MISSING_SPINE."""
        files = _good_files()
        files["content.opf"] = (
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>T</dc:title><dc:language>en</dc:language>"
            "<dc:identifier>i</dc:identifier></metadata>"
            '<manifest><item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/></manifest>'
            "</package>"
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "nospine.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("MISSING_SPINE", codes)

    def test_invalid_manifest_item_missing_attrs(self) -> None:
        """Manifest items lacking id or href are individually flagged."""
        files = _good_files()
        files["content.opf"] = build_opf(
            items=(
                '<item href="orphan.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="ch1" href="ch1.xhtml"'
                ' media-type="application/xhtml+xml"/>'
            ),
            refs='<itemref idref="ch1"/>',
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "item.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertEqual(codes.count("INVALID_MANIFEST_ITEM"), 1)
        self.assertNotIn("SPINE_IDREF_NOT_IN_MANIFEST", codes)

    def test_manifest_item_references_missing_files(self) -> None:
        """Missing manifest targets are flagged once per item type."""
        files = _good_files()
        files["content.opf"] = build_opf(
            items=(
                '<item id="ghost" href="ghost.xhtml"'
                ' media-type="application/xhtml+xml"/>'
                '<item id="pic" href="pic.png" media-type="image/png"/>'
                '<item id="ch1" href="ch1.xhtml"'
                ' media-type="application/xhtml+xml"/>'
            ),
            refs='<itemref idref="ch1"/>',
        )
        with TemporaryDirectory() as tmpdir:
            epub = write_epub(tmpdir, "miss.epub", files)
            doctor = EpubDoctor(epub, max_img_size_kb=10.0)
            report = doctor.run_diagnostics()
        codes = [i["code"] for i in report["issues"]]
        self.assertEqual(codes.count("MISSING_MANIFEST_FILE"), 2)
        # Missing assets must not crash xml/oversize validators.
        self.assertNotIn("OVERSIZED_IMAGE", codes)
        self.assertNotIn("XML_SYNTAX_ERROR", codes)

    def test_toc_detection_via_ncx_and_spine_attr(self) -> None:
        """NCX manifest items and spine toc attributes set toc_path."""
        ncx = (
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            "<head/><docTitle><text>T</text></docTitle></ncx>"
        )
        files = _good_files()
        files["toc.ncx"] = ncx
        files["content.opf"] = build_opf(
            items=(
                '<item id="ncx-toc" href="toc.ncx"'
                ' media-type="application/x-dtbncx+xml"/>'
                '<item id="ch1" href="ch1.xhtml"'
                ' media-type="application/xhtml+xml"/>'
            ),
            refs='<itemref idref="ch1"/>',
        )
        # Give the spine a toc attribute pointing at the NCX manifest id.
        files["content.opf"] = files["content.opf"].replace(
            "<spine>", '<spine toc="ncx-toc">'
        )
        with TemporaryDirectory() as tmpdir:
            doctor = EpubDoctor(write_epub(tmpdir, "toc.epub", files))
            doctor.run_diagnostics()
        self.assertEqual(doctor.toc_path, "toc.ncx")


class TestSpineAndLinkChecks(unittest.TestCase):
    """Tests for spine integrity and HTML link validation."""

    def test_spine_idref_problems_flagged(self) -> None:
        """Unknown and duplicated idrefs produce distinct issues."""
        files = _good_files()
        files["content.opf"] = build_opf(
            items=(
                '<item id="ch1" href="ch1.xhtml"'
                ' media-type="application/xhtml+xml"/>'
            ),
            refs=(
                "<itemref/>"
                '<itemref idref="ghost"/>'
                '<itemref idref="ch1"/>'
                '<itemref idref="ch1"/>'
            ),
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "spine.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("SPINE_IDREF_NOT_IN_MANIFEST", codes)
        self.assertIn("DUPLICATE_SPINE_ITEM", codes)

    def test_broken_xml_content_flagged(self) -> None:
        """Malformed XHTML payloads yield XML_SYNTAX_ERROR."""
        files = _good_files()
        files["ch1.xhtml"] = "<html><body><p>Unclosed paragraph"
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "badxml.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("XML_SYNTAX_ERROR", codes)

    def test_fragment_only_link_resolves_against_self(self) -> None:
        """#fragment links target their own file's anchor IDs."""
        files = _good_files()
        files["ch1.xhtml"] = (
            "<html><body>"
            '<h1 id="top">Start</h1>'
            '<a name="named-anchor"></a>'
            '<a href="#top">Jump</a>'
            '<a href="#named-anchor">Named</a>'
            '<a href="#void">Bad</a>'
            "</body></html>"
        )
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "frag.epub", files))
        anchors = [i for i in report["issues"] if i["code"] == "BROKEN_ANCHOR_FRAGMENT"]
        self.assertEqual(len(anchors), 1)
        self.assertIn("#void", anchors[0]["message"])

    def test_orphaned_files_detected(self) -> None:
        """Files present in the zip but absent from the manifest are flagged."""
        files = _good_files()
        files["stray.txt"] = "leftover"
        with TemporaryDirectory() as tmpdir:
            report = run_doctor(write_epub(tmpdir, "orphan.epub", files))
        codes = [i["code"] for i in report["issues"]]
        self.assertIn("ORPHANED_FILE", codes)


class TestReportFormatting(unittest.TestCase):
    """Tests for text report rendering of diagnostic results."""

    @staticmethod
    def _report(issues: list) -> dict:
        """Build a minimal report dictionary."""
        return {
            "epub_path": "sample.epub",
            "status": "FAIL" if issues else "PASS",
            "summary": {
                "CRITICAL": (
                    1 if any(i["severity"] == "CRITICAL" for i in issues) else 0
                ),
                "ERROR": len([i for i in issues if i["severity"] == "ERROR"]),
                "WARNING": 0,
                "INFO": 0,
            },
            "issues": issues,
        }

    def test_clean_report_has_no_issues_section(self) -> None:
        """PASS reports end with the clean-scan message."""
        text = format_text_report(self._report([]))
        self.assertIn("EPUB DOCTOR DIAGNOSTIC REPORT", text)
        self.assertIn("No structural errors or warnings detected.", text)

    def test_issue_lines_include_location_and_message(self) -> None:
        """Each issue renders an index, severity, code, location, message."""
        text = format_text_report(
            self._report(
                [
                    {
                        "severity": "ERROR",
                        "code": "X_Y",
                        "message": "msg",
                        "location": "loc.xhtml",
                    }
                ]
            )
        )
        self.assertIn("#1 [ERROR] X_Y [loc.xhtml]", text)
        self.assertIn("msg", text)


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def _run_main(self, argv: list) -> tuple:
        """Run main() with patched argv; return (code, stdout)."""
        stdout = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout):
            with mock.patch.object(sys, "argv", ["main.py"] + argv):
                try:
                    main_module.main()
                except SystemExit as exc:
                    code = int(exc.code if exc.code is not None else 0)
        return code, stdout.getvalue()

    def test_pass_run_text_exit_zero(self) -> None:
        """Healthy epubs print the report header and exit 0."""
        with TemporaryDirectory() as tmpdir:
            epub = write_epub(tmpdir, "good.epub", _good_files())
            code, out = self._run_main([str(epub)])
        self.assertEqual(code, 0)
        self.assertIn("EPUB DOCTOR DIAGNOSTIC REPORT", out)
        self.assertIn("Status: PASS", out)

    def test_fail_run_exits_one(self) -> None:
        """Broken epubs exit 1 after printing FAIL status."""
        code, out = self._run_main(["Z:/no/such/book.epub"])
        self.assertEqual(code, 1)
        self.assertIn("Status: FAIL", out)

    def test_json_output_parseable(self) -> None:
        """--json emits a machine-readable report object."""
        with TemporaryDirectory() as tmpdir:
            epub = write_epub(tmpdir, "good.epub", _good_files())
            code, out = self._run_main([str(epub), "--json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["status"], "PASS")
        self.assertIn("summary", report)

    def test_output_option_writes_report_file(self) -> None:
        """--output saves the report to disk instead of only stdout."""
        with TemporaryDirectory() as tmpdir:
            epub = write_epub(tmpdir, "good.epub", _good_files())
            dest = Path(tmpdir) / "report.txt"
            code, out = self._run_main([str(epub), "--output", str(dest)])
            self.assertEqual(code, 0)
            self.assertIn(f"Report written to {dest}", out)
            saved = dest.read_text(encoding="utf-8")
        self.assertIn("EPUB DOCTOR DIAGNOSTIC REPORT", saved)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for epub-doctor tool."""

import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from main import EpubDoctor


def create_test_epub_zip(files_dict: dict) -> bytes:
    """Helper to generate in-memory EPUB zip file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for filename, content in files_dict.items():
            if isinstance(content, str):
                z.writestr(filename, content.encode("utf-8"))
            else:
                z.writestr(filename, content)
    return buf.getvalue()


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


if __name__ == "__main__":
    unittest.main()

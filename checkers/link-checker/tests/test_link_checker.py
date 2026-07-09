"""Tests for link_checker.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-argument,too-few-public-methods
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure the parent directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from link_checker import (  # noqa: E402
    LinkResult,
    build_summary,
    check_url,
    extract_links_from_html,
    extract_links_from_markdown,
    scan_local_files,
)


# ---------------------------------------------------------------------------
# extract_links_from_markdown
# ---------------------------------------------------------------------------
class TestExtractLinksFromMarkdown:
    def test_inline_link(self) -> None:
        content = "[Example](https://example.com)"
        links = extract_links_from_markdown(content, "test.md")
        assert ("https://example.com", "test.md") in links

    def test_reference_link(self) -> None:
        content = "[Example]: https://example.com"
        links = extract_links_from_markdown(content, "test.md")
        assert ("https://example.com", "test.md") in links

    def test_anchor_link_ignored(self) -> None:
        content = "[Top](#top)"
        links = extract_links_from_markdown(content, "test.md")
        assert links == []

    def test_multiple_links(self) -> None:
        content = "[A](https://a.com) and [B](https://b.com)"
        links = extract_links_from_markdown(content, "test.md")
        urls = [u for u, _ in links]
        assert "https://a.com" in urls
        assert "https://b.com" in urls

    def test_link_with_title_stripped(self) -> None:
        content = '[Foo](https://foo.com "Foo Title")'
        links = extract_links_from_markdown(content, "test.md")
        urls = [u for u, _ in links]
        assert "https://foo.com" in urls


# ---------------------------------------------------------------------------
# extract_links_from_html
# ---------------------------------------------------------------------------
class TestExtractLinksFromHtml:
    def test_href_link(self) -> None:
        html = '<a href="https://example.com">click</a>'
        links = extract_links_from_html(html, "https://page.com")
        assert ("https://example.com", "https://page.com") in links

    def test_relative_link_resolved(self) -> None:
        html = '<a href="/about">About</a>'
        links = extract_links_from_html(html, "https://example.com")
        urls = [u for u, _ in links]
        assert "https://example.com/about" in urls

    def test_javascript_ignored(self) -> None:
        html = '<a href="javascript:void(0)">JS</a>'
        links = extract_links_from_html(html, "https://example.com")
        assert links == []

    def test_anchor_ignored(self) -> None:
        html = '<a href="#section">Section</a>'
        links = extract_links_from_html(html, "https://example.com")
        assert links == []

    def test_src_link(self) -> None:
        html = '<img src="https://img.example.com/logo.png" />'
        links = extract_links_from_html(html, "https://example.com")
        assert ("https://img.example.com/logo.png", "https://example.com") in links


# ---------------------------------------------------------------------------
# check_url
# ---------------------------------------------------------------------------
class TestCheckUrl:
    def _make_response(
        self, status: int, url: str = "https://example.com"
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.url = url
        resp.headers = {"content-type": "text/html"}
        return resp

    @patch("link_checker.requests.Session")
    def test_ok_response(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(200)
        result = check_url("https://example.com", "test.md", session, 10)
        assert result.category == "ok"
        assert result.status_code == 200

    @patch("link_checker.requests.Session")
    def test_dead_404(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(404)
        result = check_url("https://example.com/missing", "test.md", session, 10)
        assert result.category == "dead"
        assert result.status_code == 404

    @patch("link_checker.requests.Session")
    def test_redirect(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        resp = self._make_response(301)
        resp.url = "https://example.com/new"
        session.head.return_value = resp
        result = check_url("https://example.com/old", "test.md", session, 10)
        assert result.category == "redirect"
        assert result.final_url == "https://example.com/new"

    @patch("link_checker.requests.Session")
    def test_timeout(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.side_effect = requests.exceptions.Timeout()
        result = check_url("https://slow.example.com", "test.md", session, 5)
        assert result.category == "timeout"
        assert result.status_code is None

    @patch("link_checker.requests.Session")
    def test_connection_error(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.side_effect = requests.exceptions.ConnectionError("refused")
        result = check_url("https://dead.example.com", "test.md", session, 10)
        assert result.category == "error"

    @patch("link_checker.requests.Session")
    def test_head_405_fallback_to_get(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(405)
        session.get.return_value = self._make_response(200)
        result = check_url("https://example.com", "test.md", session, 10)
        assert result.category == "ok"
        session.get.assert_called_once()


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------
class TestBuildSummary:
    def _make_result(self, category: str) -> LinkResult:
        return LinkResult(
            url="https://example.com",
            status_code=200 if category == "ok" else None,
            category=category,
            final_url=None,
            error_message=None,
            source="test.md",
        )

    def test_counts(self) -> None:
        results = [
            self._make_result("ok"),
            self._make_result("ok"),
            self._make_result("dead"),
            self._make_result("redirect"),
            self._make_result("timeout"),
            self._make_result("error"),
        ]
        summary = build_summary(results)
        assert summary.total == 6
        assert summary.ok == 2
        assert summary.dead == 1
        assert summary.redirects == 1
        assert summary.timeouts == 1
        assert summary.errors == 1


# ---------------------------------------------------------------------------
# scan_local_files
# ---------------------------------------------------------------------------
class TestScanLocalFiles:
    def test_markdown_file_links(self, tmp_path: Path) -> None:
        md = tmp_path / "README.md"
        md.write_text("[Link](https://external.com)\n[Relative](./page.md)")
        links = scan_local_files(str(tmp_path), (".md",), None)
        urls = [u for u, _ in links]
        assert "https://external.com" in urls
        # Relative links without base_url are excluded
        assert all("./page.md" not in u for u in urls)

    def test_markdown_relative_with_base_url(self, tmp_path: Path) -> None:
        md = tmp_path / "docs.md"
        md.write_text("[Guide](./guide.md)")
        links = scan_local_files(str(tmp_path), (".md",), "https://example.com/docs/")
        urls = [u for u, _ in links]
        assert "https://example.com/docs/guide.md" in urls

    def test_html_file_links(self, tmp_path: Path) -> None:
        html = tmp_path / "index.html"
        html.write_text('<a href="https://example.com">Ex</a>')
        links = scan_local_files(str(tmp_path), (".html",), None)
        urls = [u for u, _ in links]
        assert "https://example.com" in urls


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------
import csv  # noqa: E402
import json  # noqa: E402

from link_checker import (  # noqa: E402
    build_session,
    crawl_website,
    export_report,
    print_report,
    run_checks,
)


def test_build_session() -> None:
    """Test build_session configuration."""
    session = build_session("TestAgent", 5)
    assert session.headers["User-Agent"] == "TestAgent"
    assert "http://" in session.adapters
    assert "https://" in session.adapters


@patch("link_checker.requests.Session")
def test_check_url_request_exception(mock_session_cls: MagicMock) -> None:
    """Test check_url handling a generic RequestException."""
    session = MagicMock()
    session.head.side_effect = requests.exceptions.RequestException("generic error")
    result = check_url("https://error.example.com", "test.md", session, 10)
    assert result.category == "error"
    assert result.error_message == "generic error"


def test_crawl_website_scenarios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test crawl_website with various page contents and depth settings."""
    session = MagicMock()

    # Page 1 (HTML): contains one internal link and one external link
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.url = "https://example.com/start"
    resp1.headers = {"content-type": "text/html"}
    resp1.text = (
        '<a href="https://example.com/page2">Page2</a> '
        '<a href="https://external.com">Ext</a>'
    )

    # Page 2 (HTML): returns timeout
    def mock_get(url, *args, **kwargs):
        if url == "https://example.com/start":
            return resp1
        elif url == "https://example.com/page2":
            raise requests.exceptions.Timeout("Timeout error")
        raise requests.exceptions.RequestException("Failed get")

    session.get = mock_get

    # 1. crawl with same_domain_only = True
    external, internal = crawl_website(
        "https://example.com/start",
        session,
        timeout=5,
        max_depth=2,
        same_domain_only=True,
    )
    assert len(external) == 1
    assert external[0] == ("https://external.com", "https://example.com/start")
    assert len(internal) == 2
    assert internal[0].url == "https://example.com/start"
    assert internal[1].url == "https://example.com/page2"
    assert internal[1].category == "timeout"

    # 2. crawl with same_domain_only = False
    # In this case, external.com is added to the crawl queue and crawled.
    # Page external.com throws RequestException
    external_any, internal_any = crawl_website(
        "https://example.com/start",
        session,
        timeout=5,
        max_depth=0,
        same_domain_only=False,
    )
    # Since depth is 1, it will crawl start, discover page2 and external.com,
    # but not crawl them because depth limit (1) is reached.
    assert len(external_any) == 0  # everything goes to crawl queue
    assert len(internal_any) == 1  # only start is crawled
    assert internal_any[0].url == "https://example.com/start"


def test_run_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_checks thread pool executor execution."""
    session = MagicMock()

    # Mock check_url
    def mock_check_url(url, source, sess, timeout):
        return LinkResult(url, 200, "ok", None, None, source)

    monkeypatch.setattr("link_checker.check_url", mock_check_url)

    links = [
        ("https://a.com", "file.md"),
        ("https://b.com", "file.md"),
        ("https://a.com", "another.md"),
    ]
    results = run_checks(links, session, 5, 2)
    assert len(results) == 2  # deduplicated


def test_print_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test print_report helper."""
    summary = build_summary(
        [
            LinkResult("https://ok.com", 200, "ok", None, None, "file.md"),
            LinkResult(
                "https://redirect.com",
                301,
                "redirect",
                "https://new.com",
                None,
                "file.md",
            ),
            LinkResult("https://dead.com", 404, "dead", None, "Not Found", "file.md"),
        ]
    )

    # verbose = False
    print_report(summary, verbose=False)
    captured = capsys.readouterr()
    assert "https://ok.com" not in captured.out
    assert "https://dead.com" in captured.out
    assert "https://redirect.com" in captured.out

    # verbose = True
    print_report(summary, verbose=True)
    captured_v = capsys.readouterr()
    assert "https://ok.com" in captured_v.out


def test_export_report(tmp_path: Path) -> None:
    """Test export_report for json and csv formats."""
    results = [
        LinkResult("https://a.com", 200, "ok", None, None, "file.md"),
        LinkResult("https://b.com", None, "timeout", None, "Timed out", "file.md"),
    ]
    summary = build_summary(results)

    # 1. JSON
    json_path = tmp_path / "report.json"
    export_report(summary, str(json_path), "json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 2
    assert data[0]["url"] == "https://a.com"
    assert data[1]["error_message"] == "Timed out"

    # 2. CSV
    csv_path = tmp_path / "report.csv"
    export_report(summary, str(csv_path), "csv")
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 2
    assert reader[0]["url"] == "https://a.com"
    assert reader[1]["error_message"] == "Timed out"


def test_main_cli_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function execution flow for local directory scan."""
    import link_checker

    md = tmp_path / "test.md"
    md.write_text("[Link](https://a.com)")

    # 1. Check local directory
    args_local = [
        "--local",
        str(tmp_path),
        "--output",
        str(tmp_path / "out.json"),
        "--format",
        "json",
    ]

    # Mock run_checks to return dummy results
    def mock_run_checks(links_with_sources, session, timeout, workers):
        return [LinkResult("https://a.com", 200, "ok", None, None, str(md))]

    monkeypatch.setattr(link_checker, "run_checks", mock_run_checks)

    link_checker.main(args_local)
    assert (tmp_path / "out.json").exists()

    # 2. Nonexistent local dir exits 1
    args_bad = ["--local", "nonexistent_dir_123"]
    with pytest.raises(SystemExit) as exc_info:
        link_checker.main(args_bad)
    assert exc_info.value.code == 1

    # 3. Fail on dead links option exits 1 if dead links exist
    def mock_run_checks_dead(links_with_sources, session, timeout, workers):
        return [LinkResult("https://dead.com", 404, "dead", None, "Not Found", str(md))]

    monkeypatch.setattr(link_checker, "run_checks", mock_run_checks_dead)

    args_fail = ["--local", str(tmp_path), "--fail-on-dead"]
    with pytest.raises(SystemExit) as exc_info:
        link_checker.main(args_fail)
    assert exc_info.value.code == 1

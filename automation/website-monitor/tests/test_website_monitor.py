"""Unit tests for Website Change Monitor."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

# Workaround for hyphenated folder module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error,wrong-import-position
import website_monitor  # noqa: E402


class TestWebsiteMonitor(unittest.TestCase):
    """Test suite for website_monitor functions."""

    @patch("requests.get")
    def test_fetch_page_content_success(self, mock_get: MagicMock) -> None:
        """Test webpage HTML retrieval."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Hello</body></html>"
        mock_get.return_value = mock_response

        html = website_monitor.fetch_page_content("https://example.com")
        self.assertEqual(html, "<html><body>Hello</body></html>")
        mock_get.assert_called_once_with(
            "https://example.com", headers=website_monitor.DEFAULT_HEADERS, timeout=10
        )

    def test_extract_section_text_valid_selector(self) -> None:
        """Test tag exclusion and clean text parsing."""
        html = (
            "<html><body>"
            "<div class='content'>"
            "  <style>body { color: red; }</style>"
            "  <h1>Heading</h1>"
            "  <script>console.log('test')</script>"
            "  <p>Paragraph text.</p>"
            "</div>"
            "</body></html>"
        )
        text, content_hash = website_monitor.extract_section_text(html, ".content")
        # Script and style should be stripped, text should be normalized
        self.assertEqual(text, "Heading\nParagraph text.")
        self.assertTrue(len(content_hash) == 64)  # 64 hex characters for SHA-256

    def test_extract_section_text_invalid_selector(self) -> None:
        """Test exception when selector matches nothing."""
        html = "<html><body><div>Test</div></body></html>"
        with self.assertRaises(ValueError):
            website_monitor.extract_section_text(html, ".missing-class")

    @patch("requests.post")
    def test_send_webhook(self, mock_post: MagicMock) -> None:
        """Test firing webhook payloads."""
        mock_post.return_value = MagicMock(status_code=200)
        website_monitor.send_webhook("https://webhook.site/abc", {"content": "test"})
        mock_post.assert_called_once_with(
            "https://webhook.site/abc", json={"content": "test"}, timeout=10
        )

    @patch("website_monitor.fetch_page_content")
    @patch("website_monitor.send_webhook")
    def test_run_monitor_flow(
        self, mock_send_webhook: MagicMock, mock_fetch: MagicMock
    ) -> None:
        """Test monitoring cycle (initialization, change, no change)."""
        # Load and verify states with temporary file
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            # 1. First run: should initialize
            mock_fetch.return_value = (
                "<html><body><main>Initial Content</main></body></html>"
            )
            targets = [
                {
                    "name": "Test Site",
                    "url": "https://test.com",
                    "selector": "main",
                    "webhook": "https://webhook.com",
                }
            ]

            res1 = website_monitor.run_monitor(targets, temp_path)
            self.assertEqual(res1["https://test.com::main"]["status"], "initialized")
            mock_send_webhook.assert_not_called()

            # 2. Second run: content same, should be unchanged
            res2 = website_monitor.run_monitor(targets, temp_path)
            self.assertEqual(res2["https://test.com::main"]["status"], "unchanged")
            mock_send_webhook.assert_not_called()

            # 3. Third run: content modified, should trigger change status and webhook
            mock_fetch.return_value = (
                "<html><body><main>Modified Content</main></body></html>"
            )
            res3 = website_monitor.run_monitor(targets, temp_path)
            self.assertEqual(res3["https://test.com::main"]["status"], "changed")
            mock_send_webhook.assert_called_once()
        finally:
            os.remove(temp_path)

    @patch("requests.post")
    def test_send_webhook_exception(self, mock_post: MagicMock) -> None:
        """Test send_webhook logs error on exception."""
        mock_post.side_effect = requests.RequestException("Connection refused")
        # Should not raise exception
        website_monitor.send_webhook("https://webhook.site", {})

    def test_load_states_corrupted(self) -> None:
        """Test load_states returns empty dict on corrupted json or missing file."""
        self.assertEqual(website_monitor.load_states("nonexistent_states.json"), {})

        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("invalid json {")
            temp_path = tmp.name

        try:
            self.assertEqual(website_monitor.load_states(temp_path), {})
        finally:
            os.remove(temp_path)

    def test_save_states_exception(self) -> None:
        """Test save_states handles exception on invalid path."""
        # Should not raise exception
        website_monitor.save_states("", {})

    def test_load_config_exception(self) -> None:
        """Test load_config raises exception on corrupted config."""
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write("invalid json {")
            temp_path = tmp.name

        try:
            with self.assertRaises(Exception):
                website_monitor.load_config(temp_path)
        finally:
            os.remove(temp_path)

    @patch("website_monitor.fetch_page_content")
    def test_run_monitor_missing_url_and_exceptions(
        self, mock_fetch: MagicMock
    ) -> None:
        """Test run_monitor with missing URL and target parsing exceptions."""
        targets = [{"name": "Missing URL Target"}]
        results = website_monitor.run_monitor(targets, "dummy.json")
        self.assertEqual(results, {})

        # Exception raised during fetch
        mock_fetch.side_effect = requests.RequestException("Gateway Timeout")
        targets_err = [{"name": "Error Target", "url": "https://test.com"}]
        results_err = website_monitor.run_monitor(targets_err, "dummy.json")
        self.assertEqual(results_err["https://test.com::body"]["status"], "error")

    @patch("website_monitor.run_monitor")
    @patch("website_monitor.load_config")
    def test_main_cli(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        """Test main CLI entry point."""
        # 1. Mutually exclusive group: neither -u nor -c raises SystemExit 2
        with self.assertRaises(SystemExit) as exc:
            website_monitor.main([])
        self.assertEqual(exc.exception.code, 2)

        # 2. Mutually exclusive group: both -u and -c raises SystemExit 2
        with self.assertRaises(SystemExit) as exc:
            website_monitor.main(["-u", "https://test.com", "-c", "config.json"])
        self.assertEqual(exc.exception.code, 2)

        # 3. Successful run of single URL monitor
        mock_run.return_value = {
            "https://test.com::body": {
                "name": "https://test.com",
                "url": "https://test.com",
                "selector": "body",
                "status": "unchanged",
            }
        }

        import io
        from unittest.mock import patch

        f = io.StringIO()
        with patch("sys.stdout", new=f):
            website_monitor.main(["-u", "https://test.com", "--json-output"])
        self.assertIn('"status": "unchanged"', f.getvalue())

        # 4. Config file load failure exits 1
        mock_load.side_effect = Exception("Config syntax error")
        with self.assertRaises(SystemExit) as exc:
            website_monitor.main(["-c", "bad_config.json"])
        self.assertEqual(exc.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

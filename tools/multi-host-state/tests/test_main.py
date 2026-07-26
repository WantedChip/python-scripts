"""Unit tests for multi-host-state tool."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from main import (
    cluster_host_outputs,
    compute_fingerprint,
    format_cluster_summary,
    load_outputs_from_directory,
    normalize_output,
    run_ssh_host_command,
)


class TestMultiHostState(unittest.TestCase):
    """Test cases for host output normalization, clustering, and file reading."""

    def test_normalize_output_timestamps_and_ips(self):
        raw = "Server 192.168.1.100 started at 2026-07-24T19:30:00Z up 5 days, 12:34"
        normalized = normalize_output(raw)
        self.assertNotIn("192.168.1.100", normalized)
        self.assertNotIn("2026-07-24T19:30:00Z", normalized)
        self.assertIn("[IP_ADDR]", normalized)
        self.assertIn("[TIMESTAMP]", normalized)

    def test_normalize_custom_ignore_pattern(self):
        raw = "Process PID: 12345 running on node ALPHA"
        normalized = normalize_output(raw, ignore_patterns=[r"PID:\s*\d+"])
        self.assertNotIn("12345", normalized)
        self.assertIn("[FILTERED]", normalized)

    def test_compute_fingerprint(self):
        fp1 = compute_fingerprint("hello world")
        fp2 = compute_fingerprint("hello world")
        fp3 = compute_fingerprint("hello world 2")
        self.assertEqual(fp1, fp2)
        self.assertNotEqual(fp1, fp3)
        self.assertEqual(len(fp1), 12)

    def test_load_outputs_from_directory(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "web1.txt").write_text("status: ok\nmem: 4GB")
            (path / "web2.txt").write_text("status: ok\nmem: 4GB")
            (path / "db1.txt").write_text("status: error\nmem: 16GB")

            outputs = load_outputs_from_directory(path)
            self.assertEqual(len(outputs), 3)
            self.assertIn("web1", outputs)
            self.assertIn("web2", outputs)
            self.assertIn("db1", outputs)
            self.assertEqual(outputs["web1"], "status: ok\nmem: 4GB")

    def test_cluster_host_outputs(self):
        host_outputs = {
            "srv1": "CPU: 10%\nIP: 10.0.0.1\nTime: 2026-01-01T00:00:00Z",
            "srv2": "CPU: 10%\nIP: 10.0.0.2\nTime: 2026-01-01T00:05:00Z",
            "srv3": "CPU: 95%\nIP: 10.0.0.3\nTime: 2026-01-01T00:10:00Z",
        }
        clusters = cluster_host_outputs(host_outputs)
        # srv1 and srv2 should normalize to same output
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["count"], 2)
        self.assertIn("srv1", clusters[0]["hosts"])
        self.assertIn("srv2", clusters[0]["hosts"])
        self.assertEqual(clusters[1]["count"], 1)
        self.assertIn("srv3", clusters[1]["hosts"])

    def test_format_cluster_summary(self):
        clusters = [
            {
                "fingerprint": "abc123456789",
                "hosts": ["web1", "web2"],
                "normalized_sample": "status: ok",
                "raw_sample": "status: ok",
                "count": 2,
            }
        ]
        summary = format_cluster_summary(clusters)
        self.assertIn("MULTI-HOST STATE CLUSTER REPORT", summary)
        self.assertIn("Total Hosts: 2", summary)
        self.assertIn("web1, web2", summary)
        self.assertIn("status: ok", summary)

    @patch("subprocess.run")
    def test_run_ssh_host_command_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Linux 5.15.0-generic"
        mock_run.return_value = mock_proc

        host, out = run_ssh_host_command("host1.example.com", "uname -a")
        self.assertEqual(host, "host1.example.com")
        self.assertEqual(out, "Linux 5.15.0-generic")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for multi-host-state tool."""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from main import (
    build_parser,
    cluster_host_outputs,
    compute_fingerprint,
    fetch_ssh_outputs,
    format_cluster_summary,
    load_outputs_from_directory,
    main,
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


class TestNormalizationEdgeCases(unittest.TestCase):
    """Test cases for normalization robustness and error handling."""

    def test_invalid_ignore_regex_is_ignored(self) -> None:
        """A malformed regex pattern must not crash normalization."""
        raw = "disk sda status: OK"
        normalized = normalize_output(raw, ignore_patterns=["[invalid"])
        self.assertIn("disk sda status: OK", normalized)

    def test_whitespace_normalization_can_be_disabled(self) -> None:
        raw = "line one   \n   line two"
        kept = normalize_output(raw, normalize_whitespace=False)
        self.assertIn("line one   \n   line two", kept)

    def test_load_outputs_missing_directory_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_outputs_from_directory(Path("Z:/definitely/not/here"))

    def test_load_outputs_read_failure_records_error_text(self) -> None:
        """An OSError while reading a host file yields an ERROR entry."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "broken.txt").write_text("data")

            original_read = Path.read_text

            def failing_read(self: Path, *args: Any, **kwargs: Any) -> str:
                if self.name == "broken.txt":
                    raise OSError("disk failure")
                return str(original_read(self, *args, **kwargs))

            with patch.object(Path, "read_text", failing_read):
                outputs = load_outputs_from_directory(path)
            self.assertIn("ERROR: Failed to read file", outputs["broken"])


class TestSshExecution(unittest.TestCase):
    """Test cases for SSH command execution paths (fully mocked)."""

    @patch("subprocess.run")
    def test_nonzero_exit_reports_ssh_error(self, mock_run: MagicMock) -> None:
        proc = MagicMock()
        proc.returncode = 255
        proc.stderr = "Permission denied (publickey).\n"
        mock_run.return_value = proc
        _, out = run_ssh_host_command("badhost", "uptime")
        self.assertEqual(out, "SSH ERROR (code 255): Permission denied (publickey).")

    @patch("subprocess.run")
    def test_timeout_expired_is_reported(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=10)
        _, out = run_ssh_host_command("slowhost", "uptime", timeout=10)
        self.assertIn("timed out after 10s", out)

    @patch("subprocess.run")
    def test_os_error_is_reported(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("ssh binary missing")
        _, out = run_ssh_host_command("hostx", "uptime")
        self.assertIn("SSH ERROR:", out)

    @patch("subprocess.run")
    def test_key_file_and_user_are_added_to_command(self, mock_run: MagicMock) -> None:
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "ok"
        mock_run.return_value = proc

        run_ssh_host_command("h1", "id", user="admin", key_file="/keys/id_rsa")
        cmd = mock_run.call_args.args[0]
        self.assertIn("admin@h1", cmd)
        self.assertIn("/keys/id_rsa", cmd)

    @patch("subprocess.run")
    def test_fetch_ssh_outputs_collects_all_hosts(self, mock_run: MagicMock) -> None:
        """Parallel fetch returns one entry per host (SSH fully mocked)."""
        proc_a = MagicMock()
        proc_a.returncode = 0
        proc_a.stdout = "out-a"
        proc_b = MagicMock()
        proc_b.returncode = 0
        proc_b.stdout = "out-b"
        mock_run.side_effect = [proc_a, proc_b]

        results = fetch_ssh_outputs(["a", "b"], "uname -r")
        self.assertEqual(results["a"], "out-a")
        self.assertEqual(results["b"], "out-b")
        self.assertEqual(mock_run.call_count, 2)


class TestClusterSummary(unittest.TestCase):
    """Test cases for report formatting options."""

    def _sample_clusters(self) -> List[Dict[str, Any]]:
        return [
            {
                "fingerprint": "f1" * 6,
                "hosts": [f"h{i}" for i in range(3)],
                "normalized_sample": "\n".join(f"row {i}" for i in range(12)),
                "raw_sample": "raw",
                "count": 3,
            }
        ]

    def test_summary_truncates_long_samples(self) -> None:
        summary = format_cluster_summary(self._sample_clusters(), verbose=False)
        self.assertIn("(4 more lines omitted)", summary)

    def test_verbose_summary_shows_every_line(self) -> None:
        clusters = self._sample_clusters()
        summary = format_cluster_summary(clusters, verbose=True)
        self.assertNotIn("lines omitted", summary)
        self.assertIn("row 11", summary)


class TestMultiHostStateCli(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    def setUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)
        (self.work / "web1.txt").write_text(
            "status: ok\nip: 10.0.0.1 at 2026-01-01T00:00:00Z"
        )
        (self.work / "web2.txt").write_text(
            "status: ok\nip: 10.0.0.2 at 2026-01-01T00:05:00Z"
        )

    def test_build_parser_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--dir", str(self.work), "--json", "--verbose", "--output", "rep.txt"]
        )
        self.assertEqual(args.dir, str(self.work))
        self.assertTrue(args.json)
        self.assertTrue(args.verbose)
        self.assertEqual(args.output, "rep.txt")

    def test_main_requires_dir_or_hosts(self) -> None:
        with self.assertRaises(SystemExit):
            main([])

    def test_main_directory_mode_writes_json_report(self) -> None:
        out_file = self.work / "report.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--dir", str(self.work), "--json", "--output", str(out_file)])
        self.assertEqual(rc, 0)
        self.assertIn(f"Report written to {out_file}", buf.getvalue())
        data: Dict[str, Any] = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertEqual(data["total_hosts"], 2)
        self.assertEqual(data["unique_clusters"], 1)
        hosts_in_cluster = data["clusters"][0]["hosts"]
        self.assertCountEqual(hosts_in_cluster, ["web1", "web2"])

    def test_main_hosts_mode_with_mocked_subprocess(self) -> None:
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "kernel identical everywhere"
        with patch("subprocess.run", return_value=proc):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--hosts", "nodeA,nodeB", "--command", "uname -r"])
        self.assertEqual(rc, 0)
        self.assertIn("Executing 'uname -r' across 2 hosts...", buf.getvalue())
        self.assertIn("Unique Clusters: 1", buf.getvalue())

    def test_main_hosts_from_file_skips_comments(self) -> None:
        hosts_file = self.work / "hosts.lst"
        hosts_file.write_text("# production\nnodeA\nnodeB\n")
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "same output"
        with patch("subprocess.run", return_value=proc):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(
                    [
                        "--hosts",
                        str(hosts_file),
                        "--command",
                        "uname -r",
                        "--user",
                        "deploy",
                    ]
                )
        self.assertEqual(rc, 0)
        self.assertIn("across 2 hosts", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

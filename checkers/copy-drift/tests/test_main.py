"""Unit tests for copy-drift main.py."""

import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from main import (
    CodeBlock,
    compute_ngrams,
    detect_copy_drift,
    extract_blocks_from_file,
    format_text_report,
    get_file_last_mtime,
    get_git_commit_history,
    jaccard_similarity,
    tokenize_code,
)


class TestCopyDrift(unittest.TestCase):
    """Tests for structural similarity and copy drift detection."""

    def test_tokenization_and_similarity(self) -> None:
        code1 = (
            "def calculate_total(price, tax):\n"
            "    subtotal = price * 1.1\n"
            "    return subtotal + tax"
        )
        code2 = (
            "def compute_total(cost, fee):\n"
            "    subtotal = cost * 1.1\n"
            "    return subtotal + fee"
        )
        t1 = tokenize_code(code1)
        t2 = tokenize_code(code2)
        ng1 = compute_ngrams(t1)
        ng2 = compute_ngrams(t2)
        sim = jaccard_similarity(ng1, ng2)
        self.assertGreater(sim, 0.70)

    def test_drift_detection_between_files(self) -> None:
        code1 = """def process_data(records):
    results = []
    for item in records:
        if item.is_valid():
            results.append(item.transform())
    return results
"""
        code2 = """def process_items(items):
    results = []
    for item in items:
        if item.is_valid():
            results.append(item.transform())
            logger.info("Processed item")
    return results
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            p1 = Path(tmp_dir) / "file1.py"
            p2 = Path(tmp_dir) / "file2.py"

            p1.write_text(code1, encoding="utf-8")
            time.sleep(0.05)  # Ensure mtime difference
            p2.write_text(code2, encoding="utf-8")

            blocks1 = extract_blocks_from_file(p1, min_lines=3)
            blocks2 = extract_blocks_from_file(p2, min_lines=3)

            reports = detect_copy_drift(blocks1 + blocks2, similarity_threshold=0.60)
            self.assertEqual(len(reports), 1)
            self.assertIn("file2.py", reports[0].updated_file)
            self.assertIn("file1.py", reports[0].outdated_file)


class TestTokenizerHelpers(unittest.TestCase):
    """Tests for tokenization, n-gram, and similarity helpers."""

    def test_ngrams_shorter_than_window(self) -> None:
        """Token lists shorter than the window size yield a single tuple."""
        self.assertEqual(compute_ngrams(["var", "def"], n=3), {("var", "def")})

    def test_jaccard_similarity_empty_sets(self) -> None:
        """An empty set on either side yields a similarity of 0.0."""
        non_empty = compute_ngrams(["var", "var", "var"])
        self.assertEqual(jaccard_similarity(set(), non_empty), 0.0)
        self.assertEqual(jaccard_similarity(non_empty, set()), 0.0)


class TestBlockExtraction(unittest.TestCase):
    """Tests for code block extraction from files."""

    def test_extract_blocks_unreadable_file_returns_empty(self) -> None:
        """A directory path cannot be read and yields no blocks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(extract_blocks_from_file(Path(tmp_dir)), [])

    def test_extract_blocks_non_python_chunking(self) -> None:
        """Non-Python files are chunked into paragraph blocks."""
        config = "\n".join(
            [
                "host = example.com",
                "port = 443",
                "retries = 5",
                "timeout = 30",
                "",
                "user = deploy",
                "key = /keys/id_rsa",
                "region = eu-west-1",
                "verbose = true",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = Path(tmp_dir) / "deploy.ini"
            cfg.write_text(config, encoding="utf-8")
            blocks = extract_blocks_from_file(cfg, min_lines=4)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].name, "block_L1")
        self.assertEqual(blocks[1].name, "block_L6")
        self.assertEqual(blocks[1].start_line, 6)
        self.assertEqual(blocks[1].end_line, 9)

    def test_extract_blocks_broken_python_falls_back_to_chunks(self) -> None:
        """Syntax-broken .py files skip AST extraction but still chunk."""
        broken = "\n".join(
            [
                "def oops(:",
                "    return",
                "x = 1",
                "y = 2",
                "z = x + y",
            ]
        )
        tmp_path = Path(tempfile.gettempdir()) / "cd_broken_test.py"
        tmp_path.write_text(broken, encoding="utf-8")
        try:
            blocks = extract_blocks_from_file(tmp_path, min_lines=4)
            self.assertTrue(blocks)
            self.assertTrue(all(b.name.startswith("block_L") for b in blocks))
        finally:
            tmp_path.unlink()


class TestGitHistory(unittest.TestCase):
    """Tests for git commit history mapping (subprocess fully mocked)."""

    @staticmethod
    def _fake_completed_process(stdout: str) -> mock.Mock:
        """Build a fake CompletedProcess-like object."""
        proc = mock.Mock()
        proc.stdout = stdout
        return proc

    def test_git_history_parses_log_output(self) -> None:
        """COMMIT:-prefixed log lines map each file to its commits."""
        log_output = "COMMIT:abc123\nsrc/a.py\n\nCOMMIT:def456\nsrc/b.py\nsrc/a.py\n"
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            (repo / "src").mkdir()
            (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            with mock.patch(
                "subprocess.run",
                return_value=self._fake_completed_process(log_output),
            ):
                history = get_git_commit_history(repo)
        resolved_a = str((repo / "src" / "a.py").resolve())
        resolved_b = str((repo / "src" / "b.py").resolve())
        self.assertEqual(history[resolved_a], {"abc123", "def456"})
        self.assertEqual(history[resolved_b], {"def456"})

    def test_git_history_swallows_subprocess_errors(self) -> None:
        """A failing git invocation results in an empty history map."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("subprocess.run", side_effect=OSError("git not found")):
                self.assertEqual(get_git_commit_history(Path(tmp_dir)), {})

    def test_get_file_last_mtime_missing_file(self) -> None:
        """Missing files report mtime 0.0 instead of raising."""
        self.assertEqual(get_file_last_mtime("Z:/nope/missing.py"), 0.0)


class TestDriftDetectionEdgeCases(unittest.TestCase):
    """Tests for drift detection filtering rules."""

    @staticmethod
    def _make_block(file_path: str, start: int, content: str) -> CodeBlock:
        """Build a CodeBlock with tokens derived from ``content``."""
        return CodeBlock(
            file_path=file_path,
            start_line=start,
            end_line=start + content.count("\n"),
            name=f"f{start}",
            content=content,
            normalized_tokens=tokenize_code(content),
        )

    def test_identical_content_not_reported_as_drift(self) -> None:
        """Structurally similar blocks with identical bodies are not drift."""
        body = (
            "def handle(x):\n    y = x * 2\n    if y:\n        return y\n    return 0\n"
        )
        b1 = self._make_block("a.py", 1, body)
        b2 = self._make_block("b.py", 1, body)
        self.assertEqual(detect_copy_drift([b1, b2]), [])

    def test_same_start_line_in_same_file_skipped(self) -> None:
        """Blocks sharing file path and start line are ignored entirely."""
        body1 = "def one(x):\n    return x + 1\n    # pad\n    # pad\n"
        body2 = "def two(x):\n    return x + 2\n    # pad\n    # pad\n"
        b1 = self._make_block("a.py", 10, body1)
        b2 = self._make_block("a.py", 10, body2)
        self.assertEqual(detect_copy_drift([b1, b2]), [])

    def test_historical_coupling_commits_counted(self) -> None:
        """Shared commits between the two files appear in the report."""
        body1 = (
            "def alpha(a):\n    b = a * 2\n    if b:\n        return b\n    return 0\n"
        )
        body2 = (
            "def beta(c):\n    d = c * 3\n    if d:\n        return d\n    return 0\n"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            pa = Path(tmp_dir) / "a.py"
            pb = Path(tmp_dir) / "b.py"
            pa.write_text(body1, encoding="utf-8")
            time.sleep(0.05)
            pb.write_text(body2, encoding="utf-8")
            b1 = self._make_block(str(pa), 1, body1)
            b2 = self._make_block(str(pb), 1, body2)
            commits = {
                str(pa.resolve()): {"c1", "c2"},
                str(pb.resolve()): {"c2", "c3"},
            }
            reports = detect_copy_drift([b1, b2], file_commits=commits)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].historical_coupling_commits, 1)
        self.assertIn("--- ", reports[0].patch_suggestion)
        self.assertIn("+++ ", reports[0].patch_suggestion)

    def test_format_text_report_variants(self) -> None:
        """Empty input gives the clean message; populated input lists drift."""
        self.assertEqual(
            format_text_report([]),
            "No copy drift detected across structural code blocks.",
        )
        body1 = (
            "def alpha(a):\n    b = a * 2\n    if b:\n        return b\n    return 0\n"
        )
        body2 = (
            "def beta(c):\n    d = c * 3\n    if d:\n        return d\n    return 0\n"
        )
        b1 = self._make_block("a.py", 1, body1)
        b2 = self._make_block("b.py", 1, body2)
        reports = detect_copy_drift([b1, b2])
        text = format_text_report(reports)
        self.assertIn("Copy Drift Audit Report", text)
        self.assertIn("Updated Block:", text)
        self.assertIn("Outdated Block:", text)
        self.assertIn("Patch Suggestion:", text)


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def _run_main(self, argv: list) -> tuple:
        """Run main() with patched argv; return (code, stdout, stderr)."""
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with mock.patch.object(sys, "argv", ["main.py"] + argv):
                try:
                    import main

                    main.main()
                except SystemExit as exc:
                    code = int(exc.code if exc.code is not None else 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def _write_pair(self, dir_path: Path) -> None:
        """Write a drifted function pair into ``dir_path``."""
        (dir_path / "file1.py").write_text(
            "def process_data(records):\n"
            "    results = []\n"
            "    for item in records:\n"
            "        if item.is_valid():\n"
            "            results.append(item.transform())\n"
            "    return results\n",
            encoding="utf-8",
        )
        (dir_path / "file2.py").write_text(
            "def process_items(items):\n"
            "    results = []\n"
            "    for item in items:\n"
            "        if item.is_valid():\n"
            "            results.append(item.transform())\n"
            "            logger.info('done')\n"
            "    return results\n",
            encoding="utf-8",
        )

    def test_main_reports_drift_and_exits_one(self) -> None:
        """Drifted blocks produce a report and exit code 1."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_pair(Path(tmp_dir))
            code, out, err = self._run_main(
                [tmp_dir, "--similarity-threshold", "0.5", "--min-lines", "3"]
            )
        self.assertEqual(code, 1)
        self.assertIn("Copy Drift Audit Report", out)
        self.assertEqual(err, "")

    def test_main_json_clean_project_exits_zero(self) -> None:
        """A clean single-file project yields empty JSON output, exit 0."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "solo.py"
            src.write_text(
                "def only(x):\n    return x\n\n\ndef other(y):\n    return y\n",
                encoding="utf-8",
            )
            code, out, _ = self._run_main(
                [tmp_dir, "--format", "json", "--min-lines", "3"]
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), [])

    def test_main_single_file_target(self) -> None:
        """A file target is scanned directly without directory recursion."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "single.py"
            src.write_text("def solo(x):\n    return x + 1\n    # pad\n", "utf-8")
            code, out, _ = self._run_main([str(src), "--format", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), [])

    def test_main_nonexistent_path_errors(self) -> None:
        """A missing target path reports to stderr and exits 1."""
        code, _, err = self._run_main(["Z:/definitely/not/here"])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)


if __name__ == "__main__":
    unittest.main()

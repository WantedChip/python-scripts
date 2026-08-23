"""Unit tests for mutation-witness main.py."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from main import (
    MutationEvent,
    build_parser,
    compute_diff,
    compute_sha256,
    format_text_event,
    get_process_tree,
    main,
    save_mutation_event,
    take_snapshot,
    watch_file,
    wrap_command,
)


class TestMutationWitness(unittest.TestCase):
    """Tests for file snapshot, process tree inspection, and command wrapping."""

    def test_snapshot_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test.txt"
            file_path.write_text("line 1\n", encoding="utf-8")

            snap1 = take_snapshot(file_path)

            file_path.write_text("line 1\nline 2\n", encoding="utf-8")
            snap2 = take_snapshot(file_path)

            action, delta, diff = compute_diff(snap1, snap2)
            self.assertEqual(action, "MODIFIED")
            self.assertGreater(delta, 0)
            self.assertIn("line 2", diff)

    def test_wrap_command_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_file = Path(tmp_dir) / "output.txt"
            log_file = Path(tmp_dir) / "log.json"

            # Wrapped python inline command to append text
            cmd = [
                sys.executable,
                "-c",
                f"open(r'{target_file}', 'w').write('created content')",
            ]

            event = wrap_command(target_file, cmd, log_output=log_file)
            self.assertIsNotNone(event)
            if event:
                self.assertEqual(event.action, "CREATED")
                self.assertIn("created content", event.diff)
                self.assertTrue(log_file.exists())


class TestSnapshotAndHashing(unittest.TestCase):
    """Tests for snapshotting missing files and hashing edge cases."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def test_sha256_of_missing_file_is_empty(self) -> None:
        self.assertEqual(compute_sha256(self.work / "ghost.txt"), "")

    def test_snapshot_of_missing_file_reports_absence(self) -> None:
        snap = take_snapshot(self.work / "ghost.txt")
        self.assertFalse(snap.exists)
        self.assertEqual(snap.size_bytes, 0)
        self.assertEqual(snap.content, "")
        self.assertEqual(snap.sha256, "")


class TestDiffActions(unittest.TestCase):
    """Tests for CREATED/MODIFIED/DELETED diff computation."""

    def test_deleted_action_has_negative_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "gone.txt"
            target.write_text("bye\n", encoding="utf-8")
            before = take_snapshot(target)
            target.unlink()
            after = take_snapshot(target)

            action, delta, diff = compute_diff(before, after)
            self.assertEqual(action, "DELETED")
            self.assertEqual(delta, -before.size_bytes)
            self.assertIn("File deleted", diff)


class TestProcessTreeInspection(unittest.TestCase):
    """Tests for psutil-backed and fallback process tree collection."""

    def test_parent_chain_is_walked_via_psutil(self) -> None:
        grandparent = MagicMock()
        grandparent.pid = 1
        grandparent.name.return_value = "init"
        grandparent.cmdline.return_value = ["init"]
        grandparent.parent.return_value = None

        parent = MagicMock()
        parent.pid = 100
        parent.name.return_value = "bash.exe"
        parent.cmdline.return_value = ["bash"]
        parent.cwd.return_value = "/tmp"
        parent.parent.return_value = grandparent

        me = MagicMock()
        me.pid = 200
        me.name.return_value = "python.exe"
        me.cmdline.return_value = ["python", "-c", "print(1)"]
        me.cwd.return_value = "/work"
        me.parent.return_value = parent

        with patch("psutil.Process", return_value=me):
            info = get_process_tree(200)

        self.assertEqual(info.pid, 200)
        self.assertEqual(info.process_name, "python.exe")
        self.assertEqual([entry["pid"] for entry in info.parent_tree], [100, 1])

    def test_fallback_when_psutil_fails(self) -> None:
        with patch("psutil.Process", side_effect=RuntimeError("unavailable")):
            info = get_process_tree()
        self.assertEqual(len(info.parent_tree), 1)
        self.assertEqual(info.parent_tree[0]["name"], "parent_process")


class TestEventPersistenceAndFormatting(unittest.TestCase):
    """Tests for JSON log persistence and text rendering of events."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)
        self.event = MutationEvent(
            timestamp_utc="2026-08-22T10:00:00+00:00",
            target_file=str(self.work / "f.txt"),
            action="MODIFIED",
            bytes_changed=5,
            diff="+new line",
            process_info={
                "pid": 42,
                "parent_pid": 1,
                "process_name": "pytest.exe",
                "command_line": "pytest -q",
                "working_directory": str(self.work),
                "parent_tree": [{"pid": 1, "name": "init", "cmdline": "init"}],
            },
        )

    def test_save_appends_to_existing_log(self) -> None:
        log_file = self.work / "events.json"
        save_mutation_event(self.event, log_file)
        save_mutation_event(self.event, log_file)
        stored: List[Dict[str, Any]] = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(len(stored), 2)

    def test_corrupt_log_is_reset_not_crashed(self) -> None:
        log_file = self.work / "corrupt.json"
        log_file.write_text("{not valid json", encoding="utf-8")
        save_mutation_event(self.event, log_file)
        stored: List[Dict[str, Any]] = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(len(stored), 1)

    def test_format_text_event_renders_fields(self) -> None:
        text = format_text_event(self.event)
        self.assertIn("=== File Mutation Event ===", text)
        self.assertIn("Action:      MODIFIED (+5 bytes)", text)
        self.assertIn("Responsible PID: 42 (pytest.exe)", text)
        self.assertIn("+new line", text)


class TestWatchLoop(unittest.TestCase):
    """Tests for the polling watch loop."""

    def test_watch_with_tiny_duration_returns_without_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "stable.txt"
            target.write_text("stable", encoding="utf-8")
            events = watch_file(target, interval_sec=0.001, max_duration=0.01)
            self.assertEqual(events, [])

    def test_watch_detects_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "watched.txt"
            target.write_text("v1", encoding="utf-8")

            state = {"ticks": 0}

            def fake_sleep(_seconds: float) -> None:
                state["ticks"] += 1
                if state["ticks"] == 1:
                    target.write_text("v2 with more content", encoding="utf-8")
                else:
                    raise KeyboardInterrupt

            with patch("main.time.sleep", side_effect=fake_sleep):
                events = watch_file(target, interval_sec=0.001)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].action, "MODIFIED")
            self.assertGreater(events[0].bytes_changed, 0)


class TestMutationWitnessCli(unittest.TestCase):
    """End-to-end tests for the wrap/watch/report subcommands."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def test_build_parser_wrap_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["wrap", "--file", "x.txt", "--log", "l.json"])
        self.assertEqual(args.subcommand, "wrap")
        self.assertEqual(args.file, "x.txt")
        self.assertEqual(args.cmd, [])
        watch_args = parser.parse_args(
            ["watch", "--file", "x.txt", "--interval", "0.2", "--duration", "3"]
        )
        self.assertEqual(watch_args.interval, 0.2)
        report_args = parser.parse_args(["report", "l.json", "--format", "json"])
        self.assertEqual(report_args.log_file, "l.json")

    def test_main_wrap_json_output_records_event(self) -> None:
        target = self.work / "created.txt"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "wrap",
                    "--file",
                    str(target),
                    "--format",
                    "json",
                    "--",
                    sys.executable,
                    "-c",
                    f"open(r'{target}', 'w').write('payload')",
                ]
            )
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        json_start = out.index("{")
        payload: Dict[str, Any] = json.loads(out[json_start:])
        self.assertEqual(payload["action"], "CREATED")

    def test_main_wrap_without_mutation_returns_zero(self) -> None:
        target = self.work / "untouched.txt"
        target.write_text("already here", encoding="utf-8")
        rc = main(
            [
                "wrap",
                "--file",
                str(target),
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
        )
        self.assertEqual(rc, 0)

    def test_main_wrap_missing_command_errors(self) -> None:
        rc = main(["wrap", "--file", str(self.work / "a.txt"), "--"])
        self.assertEqual(rc, 1)

    def test_main_watch_short_duration(self) -> None:
        target = self.work / "calm.txt"
        target.write_text("quiet", encoding="utf-8")
        rc = main(
            [
                "watch",
                "--file",
                str(target),
                "--interval",
                "0.001",
                "--duration",
                "0.02",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)

    def test_main_report_text_and_missing_file(self) -> None:
        log_file = self.work / "events.json"
        event = {
            "timestamp_utc": "2026-08-22T00:00:00+00:00",
            "target_file": "f.txt",
            "action": "CREATED",
            "bytes_changed": 3,
            "diff": "+abc",
            "process_info": {
                "pid": 7,
                "parent_pid": 1,
                "process_name": "sh",
                "command_line": "sh -c x",
                "working_directory": ".",
                "parent_tree": [],
            },
        }
        log_file.write_text(json.dumps([event]), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["report", str(log_file)])
        self.assertEqual(rc, 0)
        self.assertIn("CREATED", buf.getvalue())

        missing_rc = main(["report", str(self.work / "nothere.json")])
        self.assertEqual(missing_rc, 1)


if __name__ == "__main__":
    unittest.main()

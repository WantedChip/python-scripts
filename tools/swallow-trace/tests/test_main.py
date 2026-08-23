"""Tests for the Swallow Trace Tool."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, List, Tuple
from unittest import mock

from main import (
    ExceptionEvent,
    SuppressedExceptionRecord,
    SwallowTracer,
    TraceSummary,
    build_parser,
    main,
    print_summary_report,
    run_and_trace,
)

SCRIPT_SWALLOWS = (
    "def risky():\n"
    "    try:\n"
    "        raise ZeroDivisionError('division by zero')\n"
    "    except ZeroDivisionError:\n"
    "        return None\n"
    "\n"
    "risky()\n"
)

SCRIPT_PRINTS = "print('hello from target')\n"

SCRIPT_WRITES_ARGS = (
    "import sys\n"
    "with open(sys.argv[1], 'w', encoding='utf-8') as handle:\n"
    "    handle.write(sys.argv[2])\n"
)

SCRIPT_CRASHES = "raise RuntimeError('kaboom')\n"


class FakeCode:
    """Minimal stand-in mimicking ``code.co_filename`` and ``co_name``."""

    def __init__(self, co_filename: str, co_name: str) -> None:
        """Store the fake filename and function name."""
        self.co_filename = co_filename
        self.co_name = co_name


class FakeFrame:
    """Minimal stand-in mimicking ``frame.f_code`` and ``frame.f_lineno``."""

    def __init__(self, co_filename: str, co_name: str, f_lineno: int) -> None:
        """Build a fake frame positioned at ``f_lineno``."""
        self.f_code = FakeCode(co_filename, co_name)
        self.f_lineno = f_lineno


def write_script(tmp_dir: str, name: str, source: str) -> str:
    """Write ``source`` to ``tmp_dir`` and return the script path."""
    path = os.path.join(tmp_dir, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    return path


def capture_stdout(func: Callable[..., Any], *args: Any) -> Tuple[Any, str]:
    """Run ``func`` while capturing stdout; return (result, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args)
    return result, buffer.getvalue()


class TestShouldTraceFile(unittest.TestCase):
    """Tests for SwallowTracer file filtering rules."""

    def test_rejects_special_and_importlib_filenames(self) -> None:
        """Filenames that are synthetic or importlib internals are skipped."""
        tracer = SwallowTracer()
        for filename in ["", "<string>", "<stdin>", "x/importlib/boot.py"]:
            with self.subTest(filename=filename):
                self.assertFalse(tracer._should_trace_file(filename))

    def test_accepts_regular_file_without_prefix(self) -> None:
        """A normal project file is traced when no prefix is configured."""
        tracer = SwallowTracer()
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = write_script(tmp_dir, "mod.py", "pass\n")
            self.assertTrue(tracer._should_trace_file(script))

    def test_stdlib_looking_paths_are_skipped_without_prefix(self) -> None:
        """Paths that look like stdlib locations are not traced by default."""
        tracer = SwallowTracer()
        self.assertFalse(tracer._should_trace_file("C:/lib/python/json.py"))

    def test_target_prefix_filters_paths(self) -> None:
        """With a target prefix only files inside it are traced."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tracer = SwallowTracer(target_prefix=tmp_dir)
            inside = os.path.join(tmp_dir, "inside.py")
            self.assertTrue(tracer._should_trace_file(inside))
            outside = r"D:\elsewhere\outside.py"
            if os.path.abspath(outside).startswith(os.path.abspath(tmp_dir)):
                self.skipTest("platform collapsed distinct paths")
            self.assertFalse(tracer._should_trace_file(outside))


class TestTraceDispatch(unittest.TestCase):
    """Unit tests driving trace_dispatch directly with synthetic frames."""

    def make_tracer_with_frame(
        self, filename: str = "target_mod.py"
    ) -> Tuple[SwallowTracer, FakeFrame]:
        """Create a tracer plus a fake frame traced under ``filename``."""
        tracer = SwallowTracer()
        frame = FakeFrame(filename, "victim", 10)
        return tracer, frame

    def test_exception_event_is_recorded(self) -> None:
        """An 'exception' event increments counters and stores a pending event."""
        tracer, frame = self.make_tracer_with_frame()
        exc_arg = (ValueError, ValueError("boom"), None)
        tracer.trace_dispatch(frame, "exception", exc_arg)
        self.assertEqual(tracer.total_raised, 1)
        pending = list(tracer.pending_exceptions.values())
        self.assertEqual(len(pending), 1)
        event = pending[0]
        self.assertEqual(event.exc_type, "ValueError")
        self.assertEqual(event.exc_message, "boom")
        self.assertEqual(event.file_name, "target_mod.py")
        self.assertEqual(event.line_number, 10)
        self.assertEqual(event.func_name, "victim")
        self.assertGreaterEqual(event.stack_depth, 0)

    def test_missing_exc_type_defaults_to_exception(self) -> None:
        """A malformed exception payload still yields an 'Exception' name."""
        tracer, frame = self.make_tracer_with_frame()
        tracer.trace_dispatch(frame, "exception", (None, None, None))
        pending = list(tracer.pending_exceptions.values())
        self.assertEqual(pending[0].exc_type, "Exception")

    def test_fallback_return_values_are_flagged(self) -> None:
        """Each documented fallback value marks a suppressed record."""
        for fallback in [None, False, 0, "", [], {}]:
            with self.subTest(fallback=fallback):
                tracer, frame = self.make_tracer_with_frame()
                tracer.trace_dispatch(frame, "exception", (KeyError, KeyError(), None))
                tracer.trace_dispatch(frame, "return", fallback)
                records = tracer.suppressed_events
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertTrue(record.is_fallback_return)
                self.assertEqual(record.return_value, repr(fallback))
                self.assertEqual(record.handler_func, "victim")
                self.assertEqual(record.exception_event.exc_type, "KeyError")
                self.assertEqual(tracer.pending_exceptions, {})

    def test_non_fallback_return_not_flagged(self) -> None:
        """A genuine recovery value is recorded without the fallback flag."""
        tracer, frame = self.make_tracer_with_frame()
        tracer.trace_dispatch(frame, "exception", (ValueError, ValueError("e"), None))
        tracer.trace_dispatch(frame, "return", "recovered")
        record = tracer.suppressed_events[0]
        self.assertFalse(record.is_fallback_return)
        self.assertEqual(record.return_value, repr("recovered"))

    def test_return_without_pending_exception_ignored(self) -> None:
        """A plain function return does not create suppression records."""
        tracer, frame = self.make_tracer_with_frame()
        tracer.trace_dispatch(frame, "return", 42)
        self.assertEqual(tracer.suppressed_events, [])
        self.assertEqual(tracer.get_summary().total_raised, 0)

    def test_untraceable_files_are_skipped(self) -> None:
        """Events from synthetic files never mutate tracer state."""
        tracer, frame = self.make_tracer_with_frame(filename="<string>")
        result = tracer.trace_dispatch(frame, "exception", (ValueError, None, None))
        self.assertEqual(tracer.total_raised, 0)
        self.assertEqual(tracer.pending_exceptions, {})
        self.assertEqual(result, tracer.trace_dispatch)


class TestTracerLifecycle(unittest.TestCase):
    """Tests around installing and removing the trace hook."""

    def test_start_installs_and_stop_restores_trace_function(self) -> None:
        """start() installs trace_dispatch and stop() restores the original."""
        tracer = SwallowTracer()
        sentinel = lambda *args: None  # noqa: E731
        with mock.patch.object(sys, "gettrace", return_value=sentinel):
            with mock.patch.object(sys, "settrace") as fake_settrace:
                tracer.start()
                tracer.stop()
        installed = [call.args[0] for call in fake_settrace.call_args_list if call.args]
        self.assertIn(tracer.trace_dispatch, installed)
        self.assertEqual(fake_settrace.call_args_list[-1], mock.call(sentinel))


class TestRunAndTrace(unittest.TestCase):
    """Integration tests for run_and_trace orchestration."""

    def run_without_real_hook(self, script: str, args: List[str]) -> TraceSummary:
        """Execute run_and_trace with stubbed sys hooks so tests stay isolated.

        Stubbing sys.settrace keeps pytest/coverage instrumentation intact
        while still exercising compile/exec/argv handling.
        """
        with mock.patch.object(sys, "settrace"):
            with mock.patch.object(sys, "gettrace", return_value=None):
                summary = run_and_trace(script, args)
        self.assertIsInstance(summary, TraceSummary)
        return summary

    def test_script_runs_with_forwarded_arguments(self) -> None:
        """The target script executes and receives forwarded CLI arguments."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = write_script(tmp_dir, "writer.py", SCRIPT_WRITES_ARGS)
            marker = os.path.join(tmp_dir, "marker.txt")
            with mock.patch.object(sys, "argv", ["pytest"]):
                self.run_without_real_hook(script, [marker, "payload"])
            with open(marker, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "payload")

    def test_script_crash_is_swallowed_by_runner(self) -> None:
        """An uncaught error in the target never propagates out of the runner."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = write_script(tmp_dir, "crasher.py", SCRIPT_CRASHES)
            summary = self.run_without_real_hook(script, [])
            self.assertIsInstance(summary, TraceSummary)


class TestReportAndCli(unittest.TestCase):
    """Tests for report rendering and CLI entry points."""

    @staticmethod
    def make_record(is_fallback: bool) -> SuppressedExceptionRecord:
        """Build one representative suppressed-exception record."""
        event = ExceptionEvent(
            exc_type="ZeroDivisionError",
            exc_message="division by zero",
            file_name="app.py",
            line_number=12,
            func_name="divide",
            stack_depth=3,
        )
        return SuppressedExceptionRecord(
            exception_event=event,
            handler_func="divide",
            handler_file="app.py",
            handler_line=14,
            return_value="None",
            is_fallback_return=is_fallback,
        )

    def test_print_summary_report_empty(self) -> None:
        """A clean run prints totals and the no-suppression notice."""
        _, output = capture_stdout(print_summary_report, TraceSummary())
        self.assertIn("Total Exceptions Raised: 0", output)
        self.assertIn("Suppressed/Caught Exceptions: 0", output)
        self.assertIn("No swallowed or suppressed exceptions detected.", output)

    def test_print_summary_report_lists_records(self) -> None:
        """Records are rendered with raise/catch locations and return values."""
        summary = TraceSummary(total_raised=2)
        summary.suppressed_records.append(self.make_record(is_fallback=True))
        _, output = capture_stdout(print_summary_report, summary)
        self.assertIn("[1] Suppressed ZeroDivisionError: 'division by zero'", output)
        self.assertIn("Raised at:  app.py:12 in function 'divide'", output)
        self.assertIn("Caught at:  app.py:14 in function 'divide'", output)
        self.assertIn("(Fallback detected: True)", output)

    def test_build_parser_forwards_remainder_args(self) -> None:
        """Arguments after the script path are passed through verbatim."""
        parser = build_parser()
        parsed = parser.parse_args(["tool.py", "--flag", "value"])
        self.assertEqual(parsed.script, "tool.py")
        self.assertEqual(parsed.args, ["--flag", "value"])

    def test_main_empty_script_name_returns_one(self) -> None:
        """An empty script argument prints help and returns exit code 1."""
        code, output = capture_stdout(main, [""])
        self.assertEqual(code, 1)
        self.assertIn("usage:", output)

    def test_main_traces_script_end_to_end(self) -> None:
        """main() traces a real swallowing script and reports exit code 0."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = write_script(tmp_dir, "swallower.py", SCRIPT_SWALLOWS)
            code, output = capture_stdout(main, [target])
            self.assertEqual(code, 0)
            self.assertIn("=== Swallow Trace Execution Report ===", output)
            self.assertIn("[1] Suppressed ZeroDivisionError", output)
            self.assertIn("(Fallback detected: True)", output)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program exits 0 after tracing a target."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = write_script(tmp_dir, "quiet.py", SCRIPT_PRINTS)
            entry = str(Path(__file__).resolve().parents[1] / "main.py")
            with mock.patch.object(sys, "argv", [entry, target]):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as ctx:
                        runpy.run_path(entry, run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
            self.assertIn("hello from target", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

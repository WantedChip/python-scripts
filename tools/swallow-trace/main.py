"""Swallow Trace Tool.

Traces Python execution to catch swallowed/suppressed exceptions and tracks their
downstream causal impact to false return values or symptom locations.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught,exec-used

import argparse
import inspect
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ExceptionEvent:
    """Record of an exception being raised."""

    exc_type: str
    exc_message: str
    file_name: str
    line_number: int
    func_name: str
    stack_depth: int


@dataclass
class SuppressedExceptionRecord:
    """Record of a caught/suppressed exception and downstream return values."""

    exception_event: ExceptionEvent
    handler_func: str
    handler_file: str
    handler_line: int
    return_value: Optional[Any] = None
    is_fallback_return: bool = False


@dataclass
class TraceSummary:
    """Summary of all traced exceptions and suppression events."""

    total_raised: int = 0
    suppressed_records: List[SuppressedExceptionRecord] = field(default_factory=list)


class SwallowTracer:
    """Traces Python execution using sys.settrace to detect suppressed exceptions."""

    def __init__(self, target_prefix: Optional[str] = None):
        self.target_prefix = os.path.abspath(target_prefix) if target_prefix else None
        self.pending_exceptions: Dict[int, ExceptionEvent] = {}
        self.suppressed_events: List[SuppressedExceptionRecord] = []
        self.total_raised = 0
        self._orig_trace: Optional[Callable[..., Any]] = None

    def _should_trace_file(self, filename: str) -> bool:
        if not filename or filename.startswith("<") or "importlib" in filename:
            return False
        abs_fn = os.path.abspath(filename)
        if self.target_prefix:
            return abs_fn.startswith(self.target_prefix)
        # Avoid tracing standard library internal modules unless desired
        is_std = "lib/python" in abs_fn.replace("\\", "/") or "Lib/" in abs_fn
        return not is_std

    def trace_dispatch(self, frame: Any, event: str, arg: Any) -> Any:
        """Dispatch trace events."""
        code = frame.f_code
        filename = code.co_filename

        if not self._should_trace_file(filename):
            return self.trace_dispatch

        frame_id = id(frame)

        if event == "exception":
            exc_type, exc_val, _ = arg
            exc_name = exc_type.__name__ if exc_type else "Exception"
            msg = str(exc_val)
            ev = ExceptionEvent(
                exc_type=exc_name,
                exc_message=msg,
                file_name=filename,
                line_number=frame.f_lineno,
                func_name=code.co_name,
                stack_depth=len(inspect.stack()),
            )
            self.pending_exceptions[frame_id] = ev
            self.total_raised += 1

        elif event == "return":
            return_val = arg
            if frame_id in self.pending_exceptions:
                exc_ev = self.pending_exceptions.pop(frame_id)
                is_fallback = return_val in (None, False, 0, "", [], {})
                rec = SuppressedExceptionRecord(
                    exception_event=exc_ev,
                    handler_func=code.co_name,
                    handler_file=filename,
                    handler_line=frame.f_lineno,
                    return_value=repr(return_val),
                    is_fallback_return=is_fallback,
                )
                self.suppressed_events.append(rec)

        return self.trace_dispatch

    def start(self) -> None:
        """Start tracing."""
        self._orig_trace = sys.gettrace()
        sys.settrace(self.trace_dispatch)

    def stop(self) -> None:
        """Stop tracing."""
        sys.settrace(self._orig_trace)

    def get_summary(self) -> TraceSummary:
        """Get summary report."""
        return TraceSummary(
            total_raised=self.total_raised,
            suppressed_records=self.suppressed_events,
        )


def run_and_trace(script_path: str, script_args: List[str]) -> TraceSummary:
    """Execute a python script under SwallowTracer and return trace summary."""
    script_path = os.path.abspath(script_path)
    tracer = SwallowTracer(target_prefix=os.path.dirname(script_path))

    sys.argv = [script_path] + script_args
    sys.path.insert(0, os.path.dirname(script_path))

    with open(script_path, "rb") as f:
        code_bytes = f.read()

    code_obj = compile(code_bytes, script_path, "exec")
    global_namespace = {
        "__file__": script_path,
        "__name__": "__main__",
        "__doc__": None,
        "__package__": None,
    }

    tracer.start()
    try:
        exec(code_obj, global_namespace)  # nosec B102
    except Exception:  # nosec B110
        pass
    finally:
        tracer.stop()

    return tracer.get_summary()


def print_summary_report(summary: TraceSummary) -> None:
    """Print clean summary report of traced suppressed exceptions."""
    print("=== Swallow Trace Execution Report ===")
    print(f"Total Exceptions Raised: {summary.total_raised}")
    print(f"Suppressed/Caught Exceptions: {len(summary.suppressed_records)}\n")

    if not summary.suppressed_records:
        print("No swallowed or suppressed exceptions detected.")
        return

    for idx, rec in enumerate(summary.suppressed_records, start=1):
        ev = rec.exception_event
        print(f"[{idx}] Suppressed {ev.exc_type}: '{ev.exc_message}'")
        print(
            f"    Raised at:  {ev.file_name}:{ev.line_number} in function"
            f" '{ev.func_name}'"
        )
        print(
            f"    Caught at:  {rec.handler_file}:{rec.handler_line} in"
            f" function '{rec.handler_func}'"
        )
        print(
            f"    Returned:   {rec.return_value} (Fallback detected:"
            f" {rec.is_fallback_return})"
        )
        print("-" * 60)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Trace Python execution and detect swallowed/suppressed exceptions."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("script", help="Path to Python script to trace")
    parser.add_argument(
        "args", nargs=argparse.REMAINDER, help="Arguments passed to script"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Swallow Trace Tool."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    if not parsed.script:
        parser.print_help()
        return 1

    summary = run_and_trace(parsed.script, parsed.args or [])
    print_summary_report(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

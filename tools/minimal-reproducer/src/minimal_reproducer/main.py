"""Minimal Reproducer Tool.

Automatically shrinks a failing JSON, CSV, or text file using Delta Debugging (ddmin)
to discover the smallest possible input that still triggers a test or command failure.
"""

# pylint: disable=duplicate-code

import argparse
import csv
import io
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


def evaluate_predicate(
    candidate_content: str,
    file_suffix: str,
    test_cmd_template: str,
    mock_evaluator: Optional[Callable[[str], bool]] = None,
) -> bool:
    """Check if candidate input content still triggers the target failure.

    Args:
        candidate_content: String content of candidate reduced file.
        file_suffix: File extension/suffix for temp file.
        test_cmd_template: Command string containing '{file}'.
        mock_evaluator: Optional mock function returning failure boolean.

    Returns:
        True if the candidate STILL fails (reproduces bug), False otherwise.
    """
    if mock_evaluator is not None:
        return mock_evaluator(candidate_content)

    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=file_suffix, encoding="utf-8"
    ) as tmp:
        tmp.write(candidate_content)
        tmp_path = tmp.name

    try:
        cmd_str = test_cmd_template.replace("{file}", tmp_path)
        cmd_parts = cmd_str.split()
        if not cmd_parts or not shutil.which(cmd_parts[0]):
            return False

        res = subprocess.run(  # nosec B603
            cmd_parts,
            capture_output=True,
            text=True,
            check=False,
        )
        # Non-zero returncode means the command FAILED (bug reproduced)
        return res.returncode != 0
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# pylint: disable=too-many-locals
def reduce_lines_ddmin(
    lines: List[str],
    suffix: str,
    cmd_template: str,
    evaluator: Optional[Callable[[str], bool]] = None,
) -> List[str]:
    """Reduce line-based text using Delta Debugging algorithm (ddmin).

    Args:
        lines: Initial list of text lines.
        suffix: File extension suffix.
        cmd_template: Command string template.
        evaluator: Optional mock evaluator.

    Returns:
        Minimal list of lines that still reproduces failure.
    """
    current = list(lines)
    n = 2

    while len(current) > 1 and n <= len(current):
        granularity = max(1, len(current) // n)
        subsets: List[List[str]] = []
        complements: List[List[str]] = []

        for i in range(0, len(current), granularity):
            subset = current[i : i + granularity]  # noqa: E203
            complement = current[:i] + current[i + granularity :]  # noqa: E203
            subsets.append(subset)
            complements.append(complement)

        reduced = False
        for comp in complements:
            if comp and evaluate_predicate(
                "\n".join(comp), suffix, cmd_template, evaluator
            ):
                current = comp
                n = max(n - 1, 2)
                reduced = True
                break

        if not reduced:
            for sub in subsets:
                if sub and evaluate_predicate(
                    "\n".join(sub), suffix, cmd_template, evaluator
                ):
                    current = sub
                    n = max(n - 1, 2)
                    reduced = True
                    break

        if not reduced:
            if n >= len(current):
                break
            n = min(n * 2, len(current))

    return current


# pylint: disable=too-many-locals
def reduce_json_object(
    obj: Union[Dict[str, Any], List[Any], Any],
    suffix: str,
    cmd_template: str,
    evaluator: Optional[Callable[[str], bool]] = None,
) -> Union[Dict[str, Any], List[Any], Any]:
    """Recursively reduce a JSON data structure (dict or list).

    Args:
        obj: Parsed JSON object, list, or scalar.
        suffix: File extension suffix.
        cmd_template: Command string template.
        evaluator: Optional mock evaluator.

    Returns:
        Reduced JSON data structure.
    """
    if isinstance(obj, dict):
        current_dict: Dict[str, Any] = dict(obj)
        keys = list(current_dict.keys())
        for key in keys:
            if len(current_dict) <= 1:
                break
            cand_dict = dict(current_dict)
            del cand_dict[key]
            cand_str = json.dumps(cand_dict, indent=2)
            if evaluate_predicate(cand_str, suffix, cmd_template, evaluator):
                current_dict = cand_dict

        # Recursively reduce dict values
        for key, val in list(current_dict.items()):
            reduced_val = reduce_json_object(val, suffix, cmd_template, evaluator)
            cand_dict = dict(current_dict)
            cand_dict[key] = reduced_val
            cand_str = json.dumps(cand_dict, indent=2)
            if evaluate_predicate(cand_str, suffix, cmd_template, evaluator):
                current_dict[key] = reduced_val

        return current_dict

    if isinstance(obj, list):
        current_list: List[Any] = list(obj)
        idx = 0
        while idx < len(current_list) and len(current_list) > 1:
            cand_list = current_list[:idx] + current_list[idx + 1 :]  # noqa: E203
            cand_str = json.dumps(cand_list, indent=2)
            if evaluate_predicate(cand_str, suffix, cmd_template, evaluator):
                current_list = cand_list
            else:
                idx += 1

        # Recursively reduce list items
        for i, item in enumerate(list(current_list)):
            reduced_item = reduce_json_object(item, suffix, cmd_template, evaluator)
            cand_list = list(current_list)
            cand_list[i] = reduced_item
            cand_str = json.dumps(cand_list, indent=2)
            if evaluate_predicate(cand_str, suffix, cmd_template, evaluator):
                current_list[i] = reduced_item

        return current_list

    return obj


def reduce_csv(
    csv_content: str,
    suffix: str,
    cmd_template: str,
    evaluator: Optional[Callable[[str], bool]] = None,
) -> str:
    """Reduce CSV rows and columns while maintaining CSV structure.

    Args:
        csv_content: Raw CSV string content.
        suffix: File suffix.
        cmd_template: Command string.
        evaluator: Optional mock evaluator.

    Returns:
        Reduced CSV content string.
    """
    reader = list(csv.reader(io.StringIO(csv_content)))
    if not reader:
        return csv_content

    header = reader[0]
    data_rows = reader[1:]

    # Reduce rows
    row_lines = [",".join(r) for r in data_rows]

    def csv_eval(cand_text: str) -> bool:
        full_csv = (
            ",".join(header) + "\n" + cand_text if cand_text else ",".join(header)
        )
        return evaluate_predicate(full_csv, suffix, cmd_template, evaluator)

    reduced_row_lines = reduce_lines_ddmin(row_lines, suffix, cmd_template, csv_eval)
    return ",".join(header) + "\n" + "\n".join(reduced_row_lines)


def shrink_minimal_reproducer(
    input_file: str,
    output_file: Optional[str] = None,
    test_cmd_template: str = "python test.py {file}",
    file_type: str = "auto",
    mock_evaluator: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Shrink input file to smallest minimal reproducer.

    Args:
        input_file: Path to initial failing file.
        output_file: Path to save reduced output.
        test_cmd_template: Command string with '{file}'.
        file_type: File format ('auto', 'json', 'csv', 'text').
        mock_evaluator: Optional mock evaluator.

    Returns:
        Dictionary summary of reduction results.
    """
    in_path = Path(input_file).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    initial_content = in_path.read_text(encoding="utf-8", errors="ignore")
    initial_bytes = len(initial_content.encode("utf-8"))
    suffix = in_path.suffix or ".txt"

    # Verify initial content reproduces failure
    if not evaluate_predicate(
        initial_content, suffix, test_cmd_template, mock_evaluator
    ):
        raise RuntimeError("Initial input file did NOT trigger failure with command!")

    determined_type = file_type.lower()
    if determined_type == "auto":
        if suffix == ".json":
            determined_type = "json"
        elif suffix == ".csv":
            determined_type = "csv"
        else:
            determined_type = "text"

    reduced_content = initial_content

    if determined_type == "json":
        try:
            parsed = json.loads(initial_content)
            reduced_obj = reduce_json_object(
                parsed, suffix, test_cmd_template, mock_evaluator
            )
            reduced_content = json.dumps(reduced_obj, indent=2)
        except json.JSONDecodeError:
            determined_type = "text"

    if determined_type == "csv":
        reduced_content = reduce_csv(
            initial_content, suffix, test_cmd_template, mock_evaluator
        )

    if determined_type == "text":
        lines = initial_content.splitlines()
        reduced_lines = reduce_lines_ddmin(
            lines, suffix, test_cmd_template, mock_evaluator
        )
        reduced_content = "\n".join(reduced_lines)

    final_bytes = len(reduced_content.encode("utf-8"))
    reduction_pct = (
        ((initial_bytes - final_bytes) / initial_bytes * 100.0)
        if initial_bytes > 0
        else 0.0
    )

    out_path_str = output_file or f"{input_file}.min"
    Path(out_path_str).write_text(reduced_content, encoding="utf-8")

    return {
        "input_file": str(in_path),
        "output_file": os.path.abspath(out_path_str),
        "file_type_used": determined_type,
        "initial_size_bytes": initial_bytes,
        "final_size_bytes": final_bytes,
        "reduction_percentage": round(reduction_pct, 2),
        "minimal_content": reduced_content,
    }


def render_text_report(report: Dict[str, Any]) -> str:
    """Format reduction report as readable text.

    Args:
        report: Analysis results dictionary.

    Returns:
        Formatted text string.
    """
    lines = [
        "=== Minimal Reproducer Reduction Report ===",
        f"Input File: {report['input_file']}",
        f"Output File: {report['output_file']}",
        f"Format Type: {report['file_type_used'].upper()}",
        f"Initial Size: {report['initial_size_bytes']} bytes",
        f"Final Minimal Size: {report['final_size_bytes']} bytes",
        f"Size Reduction: {report['reduction_percentage']}%",
        "",
        "--- Minimal Reproducer Content ---",
        report["minimal_content"],
    ]
    return "\n".join(lines)


def setup_cli() -> argparse.ArgumentParser:
    """Configure CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Shrink a failing input file (JSON, CSV, text) " "to minimal reproducer."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to initial failing input file.",
    )
    parser.add_argument(
        "--output",
        help="Path to save minimal output file (default: <input>.min).",
    )
    parser.add_argument(
        "--command",
        required=True,
        help="Failure test command containing '{file}' (e.g. 'python test.py {file}').",
    )
    parser.add_argument(
        "--type",
        choices=["auto", "json", "csv", "text"],
        default="auto",
        help="Input format type (default: auto).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output report format: text or json (default: text).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main() -> None:
    """CLI entrypoint for minimal-reproducer."""
    parser = setup_cli()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        report = shrink_minimal_reproducer(
            input_file=args.input,
            output_file=args.output,
            test_cmd_template=args.command,
            file_type=args.type,
        )

        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_text_report(report))

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Minimal reproducer reduction failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Flaky Test Hunter — Run test suite repeatedly with randomized conditions.

Shuffles test execution order and injects timing delays using a custom
temporary pytest plugin to identify and rank flaky tests.
"""

import argparse
import json
import os
import random
import subprocess  # nosec B404 - used to invoke pytest programmatically
import sys
import tempfile
from typing import Any, Dict, List


def create_plugin_file(
    plugin_path: str, seed: int, min_delay: float, max_delay: float, result_path: str
) -> None:
    """Create the temporary pytest plugin file.

    Args:
        plugin_path: Path where the plugin file should be written.
        seed: Random seed for shuffling.
        min_delay: Minimum delay in seconds.
        max_delay: Maximum delay in seconds.
        result_path: Path to write the JSON results to.
    """
    # Use raw string formatting to avoid syntax issues with backslashes on Windows
    escaped_result_path = result_path.replace("\\", "\\\\")

    content = f"""# pytest plugin for flaky test hunting
import json
import random
import time
import pytest

SEED = {seed}
MIN_DELAY = {min_delay}
MAX_DELAY = {max_delay}
RESULT_PATH = "{escaped_result_path}"

results = []

def pytest_collection_modifyitems(config, items):
    random.seed(SEED)
    random.shuffle(items)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" or (report.when == "setup" and report.failed):
        outcome_str = (
            "failed"
            if report.failed
            else "passed"
            if report.passed
            else "skipped"
        )
        results.append(
            {{
                "nodeid": item.nodeid,
                "outcome": outcome_str,
                "duration": report.duration,
            }}
        )

def pytest_runtest_setup(item):
    if MIN_DELAY > 0 or MAX_DELAY > 0:
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

def pytest_sessionfinish(session, exitstatus):
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f)
"""
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(content)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def run_test_iteration(
    pytest_path: str,
    target_path: str,
    iteration: int,
    seed: int,
    min_delay: float,
    max_delay: float,
) -> List[Dict[str, str]]:
    """Run one iteration of the test suite with randomized parameters.

    Args:
        pytest_path: Path to pytest executable.
        target_path: Directory or file to run tests in.
        iteration: Iteration index.
        seed: Random seed to use.
        min_delay: Min delay before each test.
        max_delay: Max delay before each test.

    Returns:
        A list of dictionaries representing test outcomes.
    """
    temp_dir = tempfile.gettempdir()
    plugin_name = f"_flaky_plugin_iter_{iteration}.py"
    plugin_path = os.path.join(os.getcwd(), plugin_name)
    result_name = f"_flaky_results_iter_{iteration}.json"
    result_path = os.path.join(temp_dir, result_name)

    try:
        create_plugin_file(plugin_path, seed, min_delay, max_delay, result_path)

        # Build pytest command: run pytest with target path and custom plugin
        # We strip the extension to import it as a module name
        plugin_module = plugin_name[:-3]
        cmd = [
            pytest_path,
            "-p",
            plugin_module,
            "--tb=no",
            "--no-header",
            "--no-summary",
            target_path,
        ]

        # Invoke pytest in a subprocess safely.
        # No shell=True is used; the command list is built safely and runs
        # local python test suites.
        subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

        if os.path.exists(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [
                        {str(k): str(v) for k, v in item.items()}
                        for item in data
                        if isinstance(item, dict)
                    ]
        return []

    finally:
        # Cleanup temporary files
        if os.path.exists(plugin_path):
            try:
                os.remove(plugin_path)
            except OSError:
                pass
        if os.path.exists(result_path):
            try:
                os.remove(result_path)
            except OSError:
                pass


def analyze_outcomes(all_outcomes: List[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
    """Analyze test outcomes and classify/rank tests by flakiness.

    Args:
        all_outcomes: Outcomes grouped by run iteration.

    Returns:
        List of dictionaries with test stats (nodeid, runs, passes, etc.).
    """
    stats: Dict[str, Dict[str, int]] = {}

    for run_results in all_outcomes:
        for res in run_results:
            nodeid = res["nodeid"]
            outcome = res["outcome"]

            if nodeid not in stats:
                stats[nodeid] = {"runs": 0, "passed": 0, "failed": 0, "skipped": 0}

            stats[nodeid]["runs"] += 1
            if outcome == "passed":
                stats[nodeid]["passed"] += 1
            elif outcome == "failed":
                stats[nodeid]["failed"] += 1
            elif outcome == "skipped":
                stats[nodeid]["skipped"] += 1

    report = []
    for nodeid, s in stats.items():
        total_runs = s["runs"]
        failures = s["failed"]
        passes = s["passed"]

        # Classification
        if failures > 0 and passes > 0:
            status = "FLAKY"
            rank_score = 1.0 - abs(
                0.5 - (failures / total_runs)
            )  # Highest rank when failure rate is close to 50%
        elif failures > 0:
            status = "CONSISTENTLY_FAILING"
            rank_score = 0.5
        elif s["skipped"] > 0 and total_runs == s["skipped"]:
            status = "SKIPPED"
            rank_score = 0.0
        else:
            status = "PASSED"
            rank_score = 0.0

        report.append(
            {
                "nodeid": nodeid,
                "runs": total_runs,
                "passes": passes,
                "failures": failures,
                "failure_rate": (failures / total_runs) if total_runs else 0.0,
                "status": status,
                "rank_score": rank_score,
            }
        )

    # Sort: FLAKY first (highest score), then CONSISTENTLY_FAILING, then PASSED/SKIPPED
    report.sort(
        key=lambda x: (
            x["status"] != "FLAKY",
            -float(x["rank_score"]),  # type: ignore[arg-type]
            str(x["nodeid"]),
        )
    )
    return report


def hunt_flaky_tests(
    target_path: str,
    iterations: int,
    min_delay: float,
    max_delay: float,
    pytest_path: str = "pytest",
) -> int:
    """Run hunting loop and print results.

    Args:
        target_path: Path containing tests.
        iterations: Number of test runs.
        min_delay: Min setup delay.
        max_delay: Max setup delay.
        pytest_path: Path to pytest executable.

    Returns:
        0 if successful, non-zero on failure.
    """
    print(f"Hunting flaky tests in '{target_path}' over {iterations} iterations...")
    print(f"Injected delays: {min_delay}s to {max_delay}s")

    all_outcomes = []
    for i in range(1, iterations + 1):
        seed = random.randint(
            1, 100000
        )  # nosec B311 - used for non-security shuffling seed
        print(f"Running iteration {i}/{iterations} (seed: {seed})...")
        outcomes = run_test_iteration(
            pytest_path, target_path, i, seed, min_delay, max_delay
        )
        if outcomes:
            all_outcomes.append(outcomes)

    if not all_outcomes:
        print(
            "Error: No test results were captured. "
            "Check if tests exist or pytest command is correct."
        )
        return 1

    reports = analyze_outcomes(all_outcomes)

    print("\n" + "=" * 80)
    print("                      FLAKY TEST HUNTER SUMMARY")
    print("=" * 80)

    flaky_count = sum(1 for r in reports if r["status"] == "FLAKY")
    failing_count = sum(1 for r in reports if r["status"] == "CONSISTENTLY_FAILING")

    print(f"Total Unique Tests Found: {len(reports)}")
    print(f"Flaky Tests:              {flaky_count}")
    print(f"Consistently Failing:     {failing_count}")
    print("-" * 80)

    for r in reports:
        if r["status"] == "FLAKY":
            rate_pct = r["failure_rate"] * 100
            print(
                f"[FLAKY] {r['nodeid']}\n"
                f"        Runs: {r['runs']}, Passes: {r['passes']}, "
                f"Failures: {r['failures']} (Failure Rate: {rate_pct:.1f}%)"
            )
        elif r["status"] == "CONSISTENTLY_FAILING":
            print(
                f"[FAIL ] {r['nodeid']}\n"
                f"        Runs: {r['runs']}, Passes: {r['passes']}, "
                f"Failures: {r['failures']}"
            )

    print("=" * 80)
    return 0


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "flaky-test-hunter: Identify flaky tests under " "randomized conditions."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="tests",
        help="Target test directory or file (default: tests)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of times to run the test suite (default: 5)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.0,
        help=(
            "Minimum timing delay to inject before test setups "
            "(seconds, default: 0.0)"
        ),
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=0.0,
        help=(
            "Maximum timing delay to inject before test setups "
            "(seconds, default: 0.0)"
        ),
    )
    parser.add_argument(
        "--pytest-path",
        default="pytest",
        help="Path to the pytest executable (default: pytest)",
    )

    args = parser.parse_args()
    sys.exit(
        hunt_flaky_tests(
            args.target,
            args.iterations,
            args.min_delay,
            args.max_delay,
            args.pytest_path,
        )
    )


if __name__ == "__main__":
    main()

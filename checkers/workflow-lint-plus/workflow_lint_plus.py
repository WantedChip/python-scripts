#!/usr/bin/env python3
"""Workflow Lint Plus — Advanced GitHub Actions workflow linter.

Finds issues beyond simple syntax checks: duplicate jobs, unpinned actions,
impossible/redundant conditions, missing timeouts, and cache configuration errors.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, List

import yaml  # type: ignore[import-untyped]

# SHA-1 hash regex check (40 characters hex)
SHA_PIN_PATTERN = re.compile(r"@[a-f0-9]{40}$")


def check_unpinned_actions(job_id: str, step: Dict[str, Any], idx: int) -> List[str]:
    """Check if action uses a full SHA commit hash instead of a branch/tag.

    Args:
        job_id: Job identifier.
        step: Step configuration dictionary.
        idx: Index of the step.

    Returns:
        List of warning strings.
    """
    warnings = []
    if "uses" in step:
        action = step["uses"]
        # Skip local actions (starting with ./)
        if not action.startswith("./"):
            # Check if there is a version tag
            if "@" in action:
                parts = action.split("@")
                ref = parts[-1]
                if not SHA_PIN_PATTERN.match(f"@{ref}"):
                    msg = (
                        f"Job '{job_id}' Step [{idx}] "
                        f"('{step.get('name', '')}'): Action '{action}' "
                        f"is not pinned to a full SHA commit hash (found '{ref}'). "
                        "Using branches/tags is a security risk if the tag is mutated."
                    )
                    warnings.append(msg)
            else:
                warnings.append(
                    f"Job '{job_id}' Step [{idx}]: "
                    f"Action '{action}' has no version reference."
                )
    return warnings


def check_missing_timeouts(
    job_id: str, job: Dict[str, Any], steps: List[Dict[str, Any]]
) -> List[str]:
    """Check if job or steps have timeout-minutes configured.

    Args:
        job_id: Job identifier.
        job: Job configuration dictionary.
        steps: List of step configuration dictionaries.

    Returns:
        List of warning strings.
    """
    warnings = []
    job_timeout = job.get("timeout-minutes")

    # If job has no timeout, check if every step has a timeout
    if job_timeout is None:
        step_missing = False
        for step in steps:
            if "run" in step and "timeout-minutes" not in step:
                step_missing = True
                break

        if step_missing:
            warnings.append(
                f"Job '{job_id}': Missing 'timeout-minutes' at the job level, "
                "and at least one run step lacks a timeout. Jobs can hang indefinitely."
            )
    return warnings


def check_impossible_conditions(
    context_id: str, condition: str, is_job: bool = True
) -> List[str]:
    """Check for impossible or redundant conditional statements.

    Args:
        context_id: Identifier of the job/step.
        condition: The GHA condition string.
        is_job: True if checked at job level, False if step level.

    Returns:
        List of warning strings.
    """
    warnings = []
    if not isinstance(condition, str):
        return warnings

    cond_clean = condition.replace(" ", "").lower()
    type_str = "Job" if is_job else "Step"

    # 1. success() && failure()
    if "success()" in cond_clean and "failure()" in cond_clean:
        if "&&" in cond_clean:
            warnings.append(
                f"{type_str} '{context_id}': Condition '{condition}' contains both "
                "'success()' and 'failure()' combined with '&&', which is impossible."
            )

    # 2. always() && success() (redundant)
    if "always()" in cond_clean and "success()" in cond_clean:
        warnings.append(
            f"{type_str} '{context_id}': Condition '{condition}' combines "
            "'always()' and 'success()' which is redundant (success implies always)."
        )

    # 3. always() && failure() (redundant)
    if "always()" in cond_clean and "failure()" in cond_clean:
        warnings.append(
            f"{type_str} '{context_id}': Condition '{condition}' combines "
            "'always()' and 'failure()' which is redundant."
        )

    return warnings


def check_unnecessary_matrix(job_id: str, job: Dict[str, Any]) -> List[str]:
    """Check for redundant matrix combinations (e.g. single-value keys).

    Args:
        job_id: Job identifier.
        job: Job configuration dictionary.

    Returns:
        List of warning strings.
    """
    warnings: List[str] = []
    matrix = job.get("strategy", {}).get("matrix", {})
    if not isinstance(matrix, dict):
        return warnings

    for key, val in matrix.items():
        if isinstance(val, list) and len(val) == 1:
            msg = (
                f"Job '{job_id}': Matrix key '{key}' has only one value {val}. "
                "Consider setting this directly as a normal environment "
                "variable or job input."
            )
            warnings.append(msg)
    return warnings


def check_cache_mistakes(job_id: str, step: Dict[str, Any], idx: int) -> List[str]:
    """Check for common cache setup mistakes.

    Args:
        job_id: Job identifier.
        step: Step configuration dictionary.
        idx: Index of the step.

    Returns:
        List of warning strings.
    """
    warnings = []
    uses = step.get("uses", "")

    if "actions/cache" in uses:
        # Cache action requires 'key' and 'path'
        step_with = step.get("with", {})
        if "key" not in step_with:
            warnings.append(
                f"Job '{job_id}' Step [{idx}]: using 'actions/cache' "
                "but missing the 'key' input."
            )
        if "path" not in step_with:
            warnings.append(
                f"Job '{job_id}' Step [{idx}]: using 'actions/cache' "
                "but missing the 'path' input."
            )

        # Flag outdated cache versions
        if "@v1" in uses or "@v2" in uses:
            warnings.append(
                f"Job '{job_id}' Step [{idx}]: using outdated '{uses}'. "
                "Upgrade to the latest v4 to utilize newer caching APIs."
            )

    return warnings


def check_duplicate_jobs(jobs: Dict[str, Any]) -> List[str]:
    """Check if two or more jobs contain identical execution steps.

    Args:
        jobs: Dict of all job configurations.

    Returns:
        List of warning strings.
    """
    warnings = []
    job_fingerprints: Dict[str, str] = {}

    for j_id, job_config in jobs.items():
        if not isinstance(job_config, dict):
            continue
        steps = job_config.get("steps", [])
        if not steps:
            continue

        # Create a signature of step command/action types
        fingerprint_parts = []
        for step in steps:
            if "run" in step:
                fingerprint_parts.append(f"run:{step['run'].strip()}")
            elif "uses" in step:
                fingerprint_parts.append(f"uses:{step['uses'].strip()}")

        fingerprint = "|".join(fingerprint_parts)
        if fingerprint:
            if fingerprint in job_fingerprints:
                other_job = job_fingerprints[fingerprint]
                warnings.append(
                    f"Jobs '{j_id}' and '{other_job}' appear to have "
                    "identical execution steps. Consider consolidating them "
                    "or reusing a workflow."
                )
            else:
                job_fingerprints[fingerprint] = j_id

    return warnings


def lint_workflow_file(filepath: str) -> List[str]:
    """Lint a single GitHub Actions workflow file.

    Args:
        filepath: Path to the GHA YAML file.

    Returns:
        List of warning strings.
    """
    warnings: List[str] = []
    if not os.path.exists(filepath):
        return [f"File not found: {filepath}"]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            wf = yaml.safe_load(f)
    except Exception as err:  # pylint: disable=broad-except
        return [f"YAML Parse Error in '{filepath}': {err}"]

    if not isinstance(wf, dict):
        return [f"Invalid GHA workflow layout in '{filepath}'"]

    jobs = wf.get("jobs", {})
    if not isinstance(jobs, dict):
        return [f"Invalid 'jobs' element in '{filepath}'"]

    # 1. Run cross-job duplications
    warnings.extend(check_duplicate_jobs(jobs))

    # 2. Run per-job checks
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue

        # Job condition check
        if "if" in job:
            warnings.extend(check_impossible_conditions(job_id, job["if"], is_job=True))

        # Matrix check
        warnings.extend(check_unnecessary_matrix(job_id, job))

        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue

        # Job timeout check
        warnings.extend(check_missing_timeouts(job_id, job, steps))

        # Per-step checks
        for idx, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                continue

            # Step condition check
            if "if" in step:
                warnings.extend(
                    check_impossible_conditions(
                        f"{job_id}:{step.get('name', idx)}",
                        step["if"],
                        is_job=False,
                    )
                )

            # Pinning check
            warnings.extend(check_unpinned_actions(job_id, step, idx))

            # Cache mistakes check
            warnings.extend(check_cache_mistakes(job_id, step, idx))

    return warnings


# pylint: disable=too-many-branches
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="workflow-lint-plus: Advanced GitHub Actions Workflow Linter."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[".github/workflows"],
        help="Workflow files or directories to inspect (default: .github/workflows)",
    )

    args = parser.parse_args()
    files_to_check = []

    for path in args.paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in files:
                    if f.endswith(".yml") or f.endswith(".yaml"):
                        files_to_check.append(os.path.join(root, f))
        elif os.path.isfile(path):
            files_to_check.append(path)

    if not files_to_check:
        print("No workflow files (.yml/.yaml) found to check.")
        sys.exit(0)

    total_warnings = 0
    print(f"Linting {len(files_to_check)} workflow file(s)...")
    print("=" * 80)

    for filepath in sorted(files_to_check):
        print(f"File: {filepath}")
        warnings = lint_workflow_file(filepath)
        if warnings:
            for w in warnings:
                print(f"  [WARNING] {w}")
            total_warnings += len(warnings)
        else:
            print("  ✅ No workflow issues detected.")
        print("-" * 80)

    if total_warnings > 0:
        print(f"\nCompleted with {total_warnings} warning(s).")
        sys.exit(1)
    else:
        print("\nCompleted successfully. No issues found.")
        sys.exit(0)


if __name__ == "__main__":
    main()

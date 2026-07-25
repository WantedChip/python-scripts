"""Cron Job Validator & Conflict Checker.

Validates 5-field and 6-field cron expressions, calculates upcoming execution
times, and detects potential scheduling conflicts/overlaps between cron jobs.
"""

# pylint: disable=too-many-branches,too-many-locals

import argparse
import datetime
import json
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

MONTH_NAMES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

DAY_NAMES = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}

FIELD_LIMITS = [
    (0, 59, "minute"),
    (0, 23, "hour"),
    (1, 31, "day of month"),
    (1, 12, "month"),
    (0, 7, "day of week"),
]


def parse_cron_token(
    token: str,
    min_val: int,
    max_val: int,
    name_map: Optional[Dict[str, int]] = None,
) -> Set[int]:
    """Parse a single cron field token into set of valid integer values.

    Supports: '*', '1', '1,2,3', '1-5', '*/5', '1-10/2'.
    """
    token = token.strip().upper()
    if name_map:
        for k, v in name_map.items():
            token = token.replace(k, str(v))

    result = set()
    subtokens = token.split(",")

    for sub in subtokens:
        if not sub:
            continue
        step = 1
        if "/" in sub:
            range_part, step_str = sub.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step value must be > 0: '{step_str}'")
        else:
            range_part = sub

        if range_part == "*":
            start, end = min_val, max_val
        elif "-" in range_part:
            start_str, end_str = range_part.split("-", 1)
            start, end = int(start_str), int(end_str)
            if start > end:
                raise ValueError(f"Invalid range start > end: '{sub}'")
        else:
            start = end = int(range_part)

        if start < min_val or end > max_val:
            raise ValueError(f"Value '{sub}' out of bounds ({min_val}-{max_val})")

        for v in range(start, end + 1, step):
            if min_val <= v <= max_val:
                # Normalize Sunday 7 to 0
                val = 0 if (max_val == 7 and v == 7) else v
                result.add(val)

    return result


def parse_cron_expression(expression: str) -> List[Set[int]]:
    """Parse complete cron string (5 or 6 fields) into list of allowed integer sets.

    Returns:
        List of sets corresponding to [minute, hour, day, month, weekday].
    """
    parts = expression.strip().split()
    if len(parts) == 5:
        # Standard 5-field cron
        minute_token, hour_token, dom_token, month_token, dow_token = parts
    elif len(parts) == 6:
        # 6-field cron: assume field 1 is second or field 6 is year
        is_sec = parts[0].isdigit() and int(parts[0]) <= 59
        if is_sec:
            p_min, p_hour, p_dom, p_mon, p_dow = parts[1:6]
        else:
            p_min, p_hour, p_dom, p_mon, p_dow = parts[0:5]
        minute_token, hour_token, dom_token = p_min, p_hour, p_dom
        month_token, dow_token = p_mon, p_dow
    else:
        err_msg = f"Cron expression must contain 5 or 6 fields, got {len(parts)}"
        raise ValueError(err_msg)

    minutes = parse_cron_token(minute_token, 0, 59)
    hours = parse_cron_token(hour_token, 0, 23)
    doms = parse_cron_token(dom_token, 1, 31)
    months = parse_cron_token(month_token, 1, 12, MONTH_NAMES)
    dows = parse_cron_token(dow_token, 0, 7, DAY_NAMES)

    return [minutes, hours, doms, months, dows]


def validate_cron(expression: str) -> Tuple[bool, Optional[str]]:
    """Validate syntax of cron expression."""
    try:
        parse_cron_expression(expression)
        return True, None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return False, str(exc)


def match_cron_datetime(parsed: List[Set[int]], dt: datetime.datetime) -> bool:
    """Returns True if a datetime matches the parsed cron rules."""
    minutes, hours, doms, months, dows = parsed

    if dt.minute not in minutes or dt.hour not in hours or dt.month not in months:
        return False

    # Day of week in python: Monday=0..Sunday=6. Convert to Sunday=0..Saturday=6
    py_dow = dt.weekday()
    cron_dow = (py_dow + 1) % 7

    dow_match = cron_dow in dows
    dom_match = dt.day in doms

    return dow_match and dom_match


def get_next_executions(
    expression: str,
    count: int = 5,
    start_time: Optional[datetime.datetime] = None,
) -> List[str]:
    """Calculate next `count` execution datetimes for cron expression."""
    parsed = parse_cron_expression(expression)
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(
        second=0, microsecond=0
    )
    dt = start_time or now_utc

    # Step by 1 minute forward
    dt += datetime.timedelta(minutes=1)
    executions: List[str] = []

    limit = 525600  # Scan up to 1 year of minutes
    scanned = 0

    while len(executions) < count and scanned < limit:
        if match_cron_datetime(parsed, dt):
            executions.append(dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
        dt += datetime.timedelta(minutes=1)
        scanned += 1

    return executions


def check_cron_conflicts(
    jobs: List[Tuple[str, str]], window_minutes: int = 1440
) -> List[Dict[str, Any]]:
    """Check for overlapping executions between multiple cron pairs."""
    parsed_jobs = []
    for name, cron_expr in jobs:
        try:
            p = parse_cron_expression(cron_expr)
            parsed_jobs.append((name, cron_expr, p))
        except Exception:  # nosec B112 # pylint: disable=broad-exception-caught
            continue

    conflicts = []
    start_dt = datetime.datetime.now(datetime.timezone.utc).replace(
        second=0, microsecond=0
    )

    for i in range(window_minutes):
        current_dt = start_dt + datetime.timedelta(minutes=i)
        active_jobs = [
            name
            for name, expr, parsed in parsed_jobs
            if match_cron_datetime(parsed, current_dt)
        ]
        if len(active_jobs) > 1:
            conflicts.append(
                {
                    "timestamp": current_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "conflicting_jobs": active_jobs,
                    "job_count": len(active_jobs),
                }
            )

    return conflicts


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Cron Job Validator and Conflict Checker"
    )
    parser.add_argument(
        "crons",
        nargs="*",
        help="Cron expressions to validate (quote if spaces)",
    )
    parser.add_argument(
        "-n",
        "--next-count",
        type=int,
        default=5,
        help="Number of next execution times to generate",
    )
    parser.add_argument(
        "--check-conflicts",
        action="store_true",
        help="Check for overlapping execution times",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    if not args.crons:
        parser.print_help()
        sys.exit(0)

    report: Dict[str, Any] = {"validation": [], "conflicts": []}

    job_pairs = []
    for idx, cron_str in enumerate(args.crons):
        valid, err = validate_cron(cron_str)
        item: Dict[str, Any] = {
            "expression": cron_str,
            "valid": valid,
            "error": err,
        }
        if valid:
            item["next_runs"] = get_next_executions(cron_str, count=args.next_count)
            job_pairs.append((f"Job_{idx+1}", cron_str))
        report["validation"].append(item)

    if args.check_conflicts and len(job_pairs) > 1:
        report["conflicts"] = check_cron_conflicts(job_pairs, window_minutes=1440)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== Cron Validation Results ===")
        for item in report["validation"]:
            status = "VALID" if item["valid"] else f"INVALID ({item['error']})"
            print(f"Cron: '{item['expression']}' -> {status}")
            if item["valid"]:
                print(" Next executions:")
                for run in item["next_runs"]:
                    print(f"   - {run}")

        if args.check_conflicts:
            print("\n=== Conflict Detection (Next 24h) ===")
            if report["conflicts"]:
                for conf in report["conflicts"][:10]:  # Limit output display
                    jobs_str = ", ".join(conf["conflicting_jobs"])
                    print(f" Overlap at {conf['timestamp']}: [{jobs_str}]")
            else:
                print(" No scheduling overlaps detected.")


if __name__ == "__main__":
    main()

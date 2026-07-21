#!/usr/bin/env python3
"""File Origin Tracker.

Traces downloaded file origins using NTFS Zone.Identifier streams, local
browser history downloads database records, and folder timestamps.
"""

import argparse
import glob
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Any, Dict, List


def get_zone_identifier(file_path: str) -> Dict[str, str]:
    """Retrieve Zone.Identifier Alternate Data Stream (ADS) content on Windows."""
    details: Dict[str, str] = {}

    ads_path = f"{file_path}:Zone.Identifier"
    if not os.path.exists(file_path):
        return details

    try:
        with open(ads_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    details[k.strip()] = v.strip()
    except OSError:
        pass

    return details


def chrome_time_to_datetime(chrome_time: int) -> datetime:
    """Convert Chrome WebKit microsecond timestamp to standard datetime."""
    try:
        return datetime(1601, 1, 1) + timedelta(microseconds=chrome_time)
    except (ValueError, OverflowError):
        return datetime.min


def query_chrome_edge_history(
    history_db_path: str, filename: str
) -> List[Dict[str, Any]]:
    """Query Chrome or Edge History SQLite database for matching downloads."""
    results: List[Dict[str, Any]] = []
    if not os.path.exists(history_db_path):
        return results

    temp_dir = tempfile.gettempdir()
    temp_db = os.path.join(temp_dir, "browser_history_temp.db")
    try:
        shutil.copy2(history_db_path, temp_db)
    except OSError:
        return results

    try:
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = (
                "SELECT target_path, referrer, tab_url, start_time, received_bytes "
                "FROM downloads "
                "WHERE target_path LIKE ? OR tab_url LIKE ?"
            )
            pattern = f"%{filename}%"
            cursor.execute(query, (pattern, pattern))
            rows = cursor.fetchall()

            for row in rows:
                start_time_raw = row["start_time"]
                dt = chrome_time_to_datetime(start_time_raw)
                results.append(
                    {
                        "target_path": row["target_path"],
                        "referrer": row["referrer"],
                        "tab_url": row["tab_url"],
                        "download_time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "received_bytes": row["received_bytes"],
                    }
                )
    except (OSError, sqlite3.Error):
        pass
    finally:
        try:
            os.remove(temp_db)
        except OSError:
            pass

    return results


def query_firefox_history(places_db_path: str, filename: str) -> List[Dict[str, Any]]:
    """Query Firefox places.sqlite database for matching downloads/history."""
    results: List[Dict[str, Any]] = []
    if not os.path.exists(places_db_path):
        return results

    temp_dir = tempfile.gettempdir()
    temp_db = os.path.join(temp_dir, "firefox_places_temp.db")
    try:
        shutil.copy2(places_db_path, temp_db)
    except OSError:
        return results

    try:
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = (
                "SELECT p.url, p.title, p.visit_count, p.last_visit_date "
                "FROM moz_places p "
                "WHERE p.url LIKE ? OR p.title LIKE ?"
            )
            pattern = f"%{filename}%"
            cursor.execute(query, (pattern, pattern))
            rows = cursor.fetchall()

            for row in rows:
                visit_date_raw = row["last_visit_date"]
                dt = datetime.min
                if visit_date_raw:
                    try:
                        dt = datetime.fromtimestamp(visit_date_raw / 1000000.0)
                    except (ValueError, OverflowError, OSError):
                        pass
                results.append(
                    {
                        "target_path": row["title"] or "",
                        "referrer": "",
                        "tab_url": row["url"],
                        "download_time": (
                            dt.strftime("%Y-%m-%d %H:%M:%S")
                            if visit_date_raw
                            else "unknown"
                        ),
                        "received_bytes": 0,
                    }
                )
    except (OSError, sqlite3.Error):
        pass
    finally:
        try:
            os.remove(temp_db)
        except OSError:
            pass

    return results


def find_browser_dbs() -> Dict[str, str]:
    """Find default browser history database locations on Windows."""
    paths: Dict[str, str] = {}
    user_profile = os.environ.get("USERPROFILE", "")
    if not user_profile:
        return paths

    chrome_path = os.path.join(
        user_profile,
        "AppData",
        "Local",
        "Google",
        "Chrome",
        "User Data",
        "Default",
        "History",
    )
    if os.path.exists(chrome_path):
        paths["chrome"] = chrome_path

    edge_path = os.path.join(
        user_profile,
        "AppData",
        "Local",
        "Microsoft",
        "Edge",
        "User Data",
        "Default",
        "History",
    )
    if os.path.exists(edge_path):
        paths["edge"] = edge_path

    ff_profiles_glob = os.path.join(
        user_profile,
        "AppData",
        "Roaming",
        "Mozilla",
        "Firefox",
        "Profiles",
        "*",
        "places.sqlite",
    )
    ff_matches = glob.glob(ff_profiles_glob)
    if ff_matches:
        paths["firefox"] = ff_matches[0]

    return paths


def check_surrounding_clues(file_path: str) -> List[str]:
    """Check for adjacent torrent files, logs, or description text."""
    clues = []
    dir_name = os.path.dirname(file_path) or "."
    base_name = os.path.basename(file_path)
    base_no_ext, _ = os.path.splitext(base_name)

    for f in os.listdir(dir_name):
        if f == base_name:
            continue
        if base_no_ext in f:
            _, adj_ext = os.path.splitext(f.lower())

            if adj_ext == ".torrent":
                clues.append(f"Found adjacent torrent download file: '{f}'")
            elif adj_ext in (".txt", ".log", ".nfo"):
                clues.append(f"Found description/log text file: '{f}'")
            elif adj_ext == ".json":
                clues.append(f"Found companion JSON metadata file: '{f}'")

    return clues


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Trace origin url metadata, browser downloads records, and "
            "timestamps of local files."
        )
    )
    parser.add_argument("file_path", help="Path to the file to trace.")
    parser.add_argument(
        "-b",
        "--browser-db",
        help="Custom path to browser History or places.sqlite database file.",
    )

    args = parser.parse_args()

    if not os.path.exists(args.file_path):
        print(f"File does not exist: {args.file_path}", file=sys.stderr)
        sys.exit(1)

    abs_path = os.path.abspath(args.file_path)
    filename = os.path.basename(abs_path)

    print("========================================================================")
    print(f"FILE ORIGIN REPORT: {filename}")
    print("========================================================================")
    print(f"Target Path: {abs_path}")

    try:
        stat_info = os.stat(abs_path)
        created_time = datetime.fromtimestamp(stat_info.st_ctime)
        modified_time = datetime.fromtimestamp(stat_info.st_mtime)
        print(f"Created:     {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Modified:    {modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
    except OSError as e:
        print(f"Could not read filesystem timestamps: {e}")

    print("\n--- NTFS Alternate Data Stream Info ---")
    zone_info = get_zone_identifier(abs_path)
    if zone_info:
        for k, v in zone_info.items():
            print(f"{k:<15} = {v}")
    else:
        no_zone_msg = (
            "No NTFS Zone.Identifier Alternate Data Stream found "
            "(common on non-Windows/non-NTFS or non-web downloads)."
        )
        print(no_zone_msg)

    print("\n--- Local Browser History Downloads Search ---")
    history_matches = []

    if args.browser_db:
        matches = query_chrome_edge_history(args.browser_db, filename)
        if not matches:
            matches = query_firefox_history(args.browser_db, filename)
        history_matches.extend(matches)
    else:
        browser_paths = find_browser_dbs()
        for name, db_path in browser_paths.items():
            if name in ("chrome", "edge"):
                matches = query_chrome_edge_history(db_path, filename)
            else:
                matches = query_firefox_history(db_path, filename)

            for m in matches:
                m["browser"] = name.capitalize()
            history_matches.extend(matches)

    if history_matches:
        for idx, match in enumerate(history_matches, 1):
            browser_info = f" ({match['browser']})" if "browser" in match else ""
            print(f"Match {idx}{browser_info}:")
            print(f"  Source URL: {match['tab_url']}")
            if match.get("referrer"):
                print(f"  Referrer:   {match['referrer']}")
            print(f"  Downloaded: {match['download_time']}")
            if match.get("received_bytes"):
                print(f"  File Size:  {match['received_bytes']:,} bytes")
    else:
        print(
            "No download records found matching this filename in local "
            "browser histories."
        )

    print("\n--- Adjacent Directory Clues ---")
    clues = check_surrounding_clues(abs_path)
    if clues:
        for clue in clues:
            print(f"[+] {clue}")
    else:
        print("No adjacent matching torrents or metadata log files found.")


if __name__ == "__main__":
    main()

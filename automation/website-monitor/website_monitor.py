"""Website Change Monitor.

Monitors specific HTML elements on target webpages for changes.
Fires local notifications and webhook posts on detection of content changes.
"""

# pylint: disable=duplicate-code
# Standalone script design prioritized over sharing duplicate boilerplate/helpers.


import argparse
import hashlib
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# Standard User Agent to avoid basic bot blocks
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_page_content(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """Downloads target webpage.

    Args:
        url: Target page URL.
        headers: Request headers.

    Returns:
        HTML string.
    """
    req_headers = headers if headers is not None else DEFAULT_HEADERS
    # Timeout at 10 seconds to avoid hanging indefinitely
    res = requests.get(url, headers=req_headers, timeout=10)
    res.raise_for_status()
    content = res.text
    if not isinstance(content, str):
        raise TypeError("Expected response body to be a string")
    return content


def extract_section_text(html: str, selector: str) -> Tuple[str, str]:
    """Extracts target section using CSS selector and returns cleaned text.

    Args:
        html: Source HTML content.
        selector: CSS selector.

    Returns:
        A tuple of (extracted_text, element_hash).
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one(selector)
    if not element:
        raise ValueError(f"CSS selector '{selector}' did not match any elements.")

    # Remove script, style, and iframe tags which introduce noise/dynamic shifts
    for tag in element(["script", "style", "iframe", "meta"]):
        tag.decompose()

    # Get cleaned text content
    text = element.get_text(separator="\n")
    # Normalize whitespaces to collapse dynamic layout gaps
    cleaned_lines = []
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped:
            cleaned_lines.append(line_stripped)

    normalized_text = "\n".join(cleaned_lines)
    # Compute SHA-256 hash
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    return normalized_text, content_hash


def send_webhook(webhook_url: str, payload: Dict[str, Any]) -> None:
    """Sends JSON POST request to a webhook (e.g. Slack, Discord).

    Args:
        webhook_url: The webhook HTTP URL.
        payload: Dictionary payload.
    """
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info("Webhook alert fired successfully.")
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to fire webhook: %s", e)


def load_states(state_file: str) -> Dict[str, str]:
    """Loads historical hashes.

    Args:
        state_file: Path to states JSON file.

    Returns:
        Dict mapping URL keys to hashes.
    """
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data: Dict[str, str] = json.load(f)
                return data
        except Exception as e:  # pylint: disable=broad-except
            logging.error("Failed to load states: %s", e)
    return {}


def save_states(state_file: str, states: Dict[str, str]) -> None:
    """Saves states dictionary.

    Args:
        state_file: Path to states JSON file.
        states: States dictionary.
    """
    try:
        parent = os.path.dirname(state_file)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(states, f, indent=2)
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to save states: %s", e)


def load_config(config_file: str) -> List[Dict[str, Any]]:
    """Loads multiple monitor target sites configuration.

    Args:
        config_file: Path to config JSON.

    Returns:
        List of target dictionaries.
    """
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)
            return data
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to load config file: %s", e)
        raise


def run_monitor(  # pylint: disable=too-many-locals
    targets: List[Dict[str, Any]], state_file: str
) -> Dict[str, Any]:
    """Runs content extraction and hashes check against stored states.

    Args:
        targets: List of website targets.
        state_file: Path to tracking file.

    Returns:
        Results summary mapping url/name to status.
    """
    states = load_states(state_file)
    results = {}

    for target in targets:
        name = target.get("name", "Unnamed Target")
        url = target.get("url")
        selector = target.get("selector", "body")
        webhook = target.get("webhook")

        if not url:
            logging.error("Target '%s' missing URL. Skipping.", name)
            continue

        state_key = f"{url}::{selector}"
        logging.info("Checking target '%s' at %s...", name, url)

        try:
            html = fetch_page_content(url)
            _, content_hash = extract_section_text(html, selector)

            previous_hash = states.get(state_key)
            if not previous_hash:
                logging.info("First scan of %s. Saving initial hash.", url)
                states[state_key] = content_hash
                status = "initialized"
            elif previous_hash != content_hash:
                logging.warning("Change detected on %s!", url)
                states[state_key] = content_hash
                status = "changed"

                if webhook:
                    payload = {
                        "content": f"🚨 **Website Change Detected!**\n"
                        f"**Target:** {name}\n"
                        f"**URL:** {url}\n"
                        f"**Selector:** `{selector}`"
                    }
                    send_webhook(webhook, payload)
            else:
                logging.info("No change on %s.", url)
                status = "unchanged"

            results[state_key] = {
                "name": name,
                "url": url,
                "selector": selector,
                "status": status,
            }

        except Exception as e:  # pylint: disable=broad-except
            logging.error("Failed monitoring '%s': %s", name, e)
            results[state_key] = {
                "name": name,
                "url": url,
                "selector": selector,
                "status": "error",
                "error": str(e),
            }

    save_states(state_file, states)
    return results


def main(argv: Optional[List[str]] = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Website Change Monitor: Tracks HTML sections and alerts on "
            "modifications."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--url", help="Single website URL to monitor")
    group.add_argument(
        "-c",
        "--config",
        help="Path to JSON configuration containing multiple sites",
    )

    parser.add_argument(
        "-s",
        "--selector",
        default="body",
        help="CSS selector of element to monitor (default: body)",
    )
    parser.add_argument(
        "-w",
        "--webhook",
        help="Webhook HTTP URL to post JSON alerts on single target mode",
    )
    parser.add_argument(
        "--state-file",
        default="website_states.json",
        help="Path to JSON state tracking file (default: website_states.json)",
    )
    parser.add_argument(
        "-j", "--json-output", action="store_true", help="Print monitor results as JSON"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logs"
    )

    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    targets = []
    if args.config:
        try:
            targets = load_config(args.config)
        except Exception:  # pylint: disable=broad-except
            sys.exit(1)
    else:
        # Convert CLI args to single list item format
        targets = [
            {
                "name": args.url,
                "url": args.url,
                "selector": args.selector,
                "webhook": args.webhook,
            }
        ]

    results = run_monitor(targets, args.state_file)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print("=" * 60)
        print("WEBSITE MONITOR RESULT SUMMARY")
        print("=" * 60)
        for res in results.values():
            print(f"Name:     {res['name']}")
            print(f"URL:      {res['url']}")
            print(f"Selector: {res['selector']}")
            print(f"Status:   {res['status'].upper()}")
            if res.get("error"):
                print(f"Error:    {res['error']}")
            print("-" * 60)


if __name__ == "__main__":
    main()

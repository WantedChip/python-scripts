"""Typing Speed Test CLI.

Measures typing speed (WPM) and accuracy score over randomized or selected
passages.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=broad-exception-caught,no-else-return,line-too-long


DEFAULT_PASSAGES: List[Dict[str, str]] = [
    {
        "id": "1",
        "difficulty": "easy",
        "text": "The quick brown fox jumps over the lazy dog.",
    },
    {
        "id": "2",
        "difficulty": "easy",
        "text": "Python is an easy to learn, powerful programming language.",
    },
    {
        "id": "3",
        "difficulty": "medium",
        "text": (
            "Software developer experience improves significantly with clean"
            " interfaces and automated tests."
        ),
    },
    {
        "id": "4",
        "difficulty": "medium",
        "text": (
            "Asynchronous operations allow modern applications to handle high"
            " throughput without blocking execution."
        ),
    },
    {
        "id": "5",
        "difficulty": "hard",
        "text": (
            "Polymorphism, encapsulation, and inheritance form fundamental"
            " pillars of object-oriented architecture in software design."
        ),
    },
]

HISTORY_FILE = "typing_history.json"
PASSAGES_FILE = "typing_passages.json"


class PassageManager:
    """Manages passage library loading, selection, and saving."""

    def __init__(self, filepath: str = PASSAGES_FILE) -> None:
        self.filepath = filepath
        self.passages: List[Dict[str, str]] = self.load_passages()

    def load_passages(self) -> List[Dict[str, str]]:
        """Loads passages from JSON file or returns defaults."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except Exception:
                return DEFAULT_PASSAGES.copy()
        return DEFAULT_PASSAGES.copy()

    def save_passages(self) -> None:
        """Saves current passage library to file."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.passages, f, indent=2)

    def get_passage(self, difficulty: Optional[str] = None) -> Dict[str, str]:
        """Returns a random passage, optionally filtered by difficulty."""
        candidates = self.passages
        if difficulty:
            candidates = [
                p
                for p in self.passages
                if p.get("difficulty", "").lower() == difficulty.lower()
            ]
            if not candidates:
                candidates = self.passages
        return random.choice(candidates)  # nosec B311

    def add_passage(self, text: str, difficulty: str = "medium") -> Dict[str, str]:
        """Adds a new passage to the library."""
        new_id = str(len(self.passages) + 1)
        new_item = {
            "id": new_id,
            "difficulty": difficulty.lower(),
            "text": text.strip(),
        }
        self.passages.append(new_item)
        self.save_passages()
        return new_item


class ScoreCalculator:
    """Calculates typing speed metrics (WPM, Net WPM, accuracy, errors)."""

    @staticmethod
    def calculate_wpm(typed_text: str, elapsed_seconds: float) -> float:
        """Calculates Gross Words Per Minute.

        Standard formula: (total characters typed / 5) / (elapsed seconds / 60)
        """
        if elapsed_seconds <= 0:
            return 0.0
        words = len(typed_text) / 5.0
        minutes = elapsed_seconds / 60.0
        return round(words / minutes, 2)

    @staticmethod
    def calculate_net_wpm(
        target_text: str, typed_text: str, elapsed_seconds: float
    ) -> float:
        """Calculates Net Words Per Minute considering errors.

        Formula: ((correct characters / 5) - uncorrected errors) / minutes
        """
        if elapsed_seconds <= 0:
            return 0.0

        correct_count = 0
        uncorrected_errors = 0
        min_len = min(len(target_text), len(typed_text))

        for i in range(min_len):
            if target_text[i] == typed_text[i]:
                correct_count += 1
            else:
                uncorrected_errors += 1

        uncorrected_errors += abs(len(target_text) - len(typed_text))

        correct_words = correct_count / 5.0
        error_penalty = uncorrected_errors / 5.0
        minutes = elapsed_seconds / 60.0

        net_wpm = (correct_words - error_penalty) / minutes
        return max(0.0, round(net_wpm, 2))

    @staticmethod
    def calculate_accuracy(target_text: str, typed_text: str) -> float:
        """Calculates percentage accuracy based on matching characters."""
        if not target_text:
            return 100.0

        min_len = min(len(target_text), len(typed_text))
        correct = sum(1 for i in range(min_len) if target_text[i] == typed_text[i])
        max_len = max(len(target_text), len(typed_text))

        return round((correct / max_len) * 100.0, 2)

    @staticmethod
    def highlight_errors(target_text: str, typed_text: str) -> Tuple[str, List[int]]:
        """Highlights mismatched characters between target and typed text.

        Returns a formatted visualization and list of error indices.
        """
        error_indices: List[int] = []
        highlighted: List[str] = []

        max_len = max(len(target_text), len(typed_text))

        for i in range(max_len):
            t_char = target_text[i] if i < len(target_text) else ""
            u_char = typed_text[i] if i < len(typed_text) else ""

            if t_char == u_char:
                highlighted.append(u_char)
            else:
                error_indices.append(i)
                if u_char:
                    highlighted.append(f"[{u_char} != {t_char}]")
                else:
                    highlighted.append(f"[{t_char}_MISSING]")

        return "".join(highlighted), error_indices


class HistoryManager:
    """Manages persistent score logging and history retrieval."""

    def __init__(self, filepath: str = HISTORY_FILE) -> None:
        self.filepath = filepath

    def load_history(self) -> List[Dict[str, Any]]:
        """Loads score history from file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except Exception:
                return []
        return []

    def log_score(
        self,
        gross_wpm: float,
        net_wpm: float,
        accuracy: float,
        duration: float,
        passage_id: str,
    ) -> Dict[str, Any]:
        """Logs a test result entry into history."""
        history = self.load_history()
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "gross_wpm": gross_wpm,
            "net_wpm": net_wpm,
            "accuracy": accuracy,
            "duration": round(duration, 2),
            "passage_id": passage_id,
        }
        history.append(entry)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        return entry


def run_typing_test(
    passage: Dict[str, str], history_mgr: Optional[HistoryManager] = None
) -> Dict[str, Any]:
    """Runs interactive CLI typing speed test."""
    diff_name = passage.get("difficulty", "normal").upper()
    print("\n" + "=" * 60)
    print(f"TYPING SPEED TEST (Difficulty: {diff_name})")
    print("=" * 60)
    print("\nTarget Passage:\n")
    print(f"  \"{passage['text']}\"")
    print("\nPress ENTER when you are ready to begin typing...")
    input()

    print("START TYPING NOW! (Press Enter when finished):")
    start_time = time.time()
    typed_input = input("\n> ")
    end_time = time.time()

    elapsed = end_time - start_time
    gross_wpm = ScoreCalculator.calculate_wpm(typed_input, elapsed)
    net_wpm = ScoreCalculator.calculate_net_wpm(passage["text"], typed_input, elapsed)
    accuracy = ScoreCalculator.calculate_accuracy(passage["text"], typed_input)
    highlighted_diff, errors = ScoreCalculator.highlight_errors(
        passage["text"], typed_input
    )

    print("\n" + "-" * 40)
    print("TEST RESULTS:")
    print("-" * 40)
    print(f" Time Taken: {elapsed:.2f} seconds")
    print(f" Gross WPM : {gross_wpm}")
    print(f" Net WPM   : {net_wpm}")
    print(f" Accuracy  : {accuracy}%")
    print(f" Total Errors: {len(errors)}")

    if errors:
        print("\nError Comparison Visualization:")
        print(highlighted_diff)

    if history_mgr:
        history_mgr.log_score(
            gross_wpm, net_wpm, accuracy, elapsed, passage.get("id", "0")
        )
        print("\nScore saved to history!")

    return {
        "gross_wpm": gross_wpm,
        "net_wpm": net_wpm,
        "accuracy": accuracy,
        "duration": elapsed,
        "errors": len(errors),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Typing Speed Test CLI")
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Select difficulty level",
    )
    parser.add_argument(
        "--history", action="store_true", help="View past typing test results"
    )
    parser.add_argument(
        "--list-passages", action="store_true", help="List available passages"
    )
    parser.add_argument(
        "--add-passage",
        type=str,
        help="Add a custom passage to the library",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    passage_mgr = PassageManager()
    history_mgr = HistoryManager()

    if parsed.history:
        history = history_mgr.load_history()
        if not history:
            print("No test history found.")
        else:
            print("\n=== SCORE HISTORY ===")
            for idx, entry in enumerate(history, 1):
                ts = entry.get("timestamp", "")[:19]
                gw = entry["gross_wpm"]
                nw = entry["net_wpm"]
                acc = entry["accuracy"]
                dur = entry["duration"]
                print(
                    f"{idx}. [{ts}] Gross WPM: {gw} | Net WPM: {nw} |"
                    f" Acc: {acc}% | Time: {dur}s"
                )
        return 0

    if parsed.list_passages:
        print("\n=== PASSAGE LIBRARY ===")
        for p in passage_mgr.passages:
            p_diff = p["difficulty"].upper()
            print(f"[{p['id']}] Difficulty: {p_diff}\n    \"{p['text']}\"\n")
        return 0

    if parsed.add_passage:
        diff = parsed.difficulty or "medium"
        item = passage_mgr.add_passage(parsed.add_passage, diff)
        print(f"Passage added successfully with ID {item['id']} ({diff})!")
        return 0

    passage = passage_mgr.get_passage(parsed.difficulty)
    run_typing_test(passage, history_mgr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

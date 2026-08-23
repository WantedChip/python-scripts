"""Vulture whitelist file for unused code detection across repository tools."""

# pylint: disable=pointless-statement,protected-access
from typing import Any

_: Any = None

_.threshold_date
_.homepage
_.user_found
_.has_write
_.has_read
_.remediation
_.lang
_.load_mock
_.other_file
_.parse_qsl
_.urlunparse
_.dflt
_.compared_pairs
_.full_adjacent
_.do_OPTIONS
_.do_HEAD
_.tesseract_cmd
_.victim_test
_.culprit_tests
_.seed_used
_.reproduce_command
_.on_modified
_.on_deleted
_.has_stdout_redirect
_.FIELD_LIMITS
_.expr
_.sample_value
_.toc_path
_.ignored_files
_.full_block
_.normalized_expected
_.normalized_actual
_.out_headers
_.script_type
_.html_events
_._current_tag
_.parse_github_trending_html
_.review_id
_.total_reviews
_.rating_distribution
_.bathrooms
_.open_price
_.creation_date
_.query_source
_.output_files
_.mtime_a
_.mtime_b
_.replace_token
_.command_line
_.working_directory
_.typ
_.raw_timestamp
_.total_loaded
_.destination_path
_.detected_category
_.detected_extension
_.original_extension
_.stack_depth
_.exc_tb
_.slide_index
_.timestamp_sec
_.formatted_time
_.difference_score
_.ocr_text
_.get_history
_.get_duration
_.from_markdown
_.ITALIC
_.UNDERLINE
_.get_active_session
_.calculate_total_stars

# pytest hook entry points in repo-root conftest.py (called by pytest, never
# referenced by project code)
_.pytest_collectstart

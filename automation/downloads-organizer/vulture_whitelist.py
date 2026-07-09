"""Vulture whitelist for downloads_organizer.py.

Lists names that appear unused to vulture but are actually live code:
on_created and on_moved are watchdog FileSystemEventHandler API callbacks,
called dynamically by the watchdog observer framework.
"""

from downloads_organizer import DownloadWatchHandler  # noqa: F401

DownloadWatchHandler.on_created  # noqa: F821
DownloadWatchHandler.on_moved  # noqa: F821

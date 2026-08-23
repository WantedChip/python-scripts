"""Pytest bootstrap for this repo's standalone script folders.

Every script folder here is a deliberately package-less directory with its
own ``main.py`` and a ``tests/`` subfolder whose modules use bare
``from main import ...`` imports. With ``--import-mode=importlib``, pytest
does not add the script folder itself to sys.path, so collection fails with
``ModuleNotFoundError: No module named 'main'`` before a single test runs.

This conftest restores the missing piece dynamically: whenever pytest starts
collecting a test module that lives directly inside a ``tests/`` folder, the
enclosing script folder is inserted at the front of sys.path — equivalent to
running pytest from inside the script folder. CI invokes pytest once per
tests directory, so each run sees exactly one ``main``; repo-wide local runs
also work because insertion happens per-module at collect time.
"""

import sys

import pytest


def pytest_collectstart(collector: pytest.Collector) -> None:
    """Put the enclosing script folder of a collected test module on sys.path."""
    path = getattr(collector, "path", None)
    if path is None or not path.name.endswith(".py"):
        return
    if path.parent.name != "tests":
        return
    script_dir = str(path.parent.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

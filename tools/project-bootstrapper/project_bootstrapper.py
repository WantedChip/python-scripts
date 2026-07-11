"""Project Bootstrapper.

A utility to generate standard, cross-platform Python project structures complete
with linting, testing, packaging configuration, and Github Actions CI workflows.
"""

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Tuple

# pylint: disable=duplicate-code

logger = logging.getLogger("project_bootstrapper")


# String templates for generated files

README_TEMPLATE = """# {project_name}

{description}

## Development Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
   ```

2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. Run linting checks:
   ```bash
   black --check src/
   flake8 src/
   pylint src/
   mypy src/
   ```

4. Run unit tests:
   ```bash
   pytest
   ```
"""

GITIGNORE_TEMPLATE = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Unit test / coverage reports
htmlcov/
.tox/
.nosetests/
.pytest_cache/
.mypy_cache/
vulture_whitelist.py
.vulture_files
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/

# Virtual Environments
.venv/
venv/
ENV/
env/

# IDE files
.idea/
.vscode/
*.swp
*.swo
"""

PYPROJECT_TOML_TEMPLATE = """[tool.black]
line-length = 88
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 88

[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --cov=src --cov-report=term-missing"
testpaths = [
    "tests",
]
"""

REQUIREMENTS_DEV_TEMPLATE = """black
isort
flake8
pylint
mypy
pytest
pytest-cov
"""

MAIN_PY_TEMPLATE = """\"\"\"Main entry point for {project_name}.\"\"\"

import sys


def greet(name: str) -> str:
    \"\"\"Return a personalized greeting.

    Args:
        name: Name to greet.

    Returns:
        Greeting string.
    \"\"\"
    return f"Hello, {{name}}! Welcome to {project_name}."


def main() -> None:
    \"\"\"Run CLI greeting loop.\"\"\"
    name = "Developer"
    if len(sys.argv) > 1:
        name = sys.argv[1]
    print(greet(name))


if __name__ == "__main__":
    main()
"""

TEST_MAIN_PY_TEMPLATE = """\"\"\"Tests for {project_name} main module.\"\"\"

from {project_module} import main  # pylint: disable=import-error


def test_greet() -> None:
    \"\"\"Test greeting builder function.\"\"\"
    assert main.greet("Antigravity") == "Hello, Antigravity! Welcome to {project_name}."
"""

GITHUB_CI_TEMPLATE = """name: Python CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ["3.11", "3.12"]

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-dev.txt

    - name: Lint with flake8
      run: |
        flake8 src/

    - name: Test with pytest
      run: |
        pytest
"""


def setup_logging(verbose: bool) -> None:
    """Configure logging format and verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def clean_project_name(name: str) -> Tuple[str, str]:
    """Derive safe system name and module name from user input.

    Args:
        name: raw user-supplied project name string.

    Returns:
        Tuple of (clean_project_name, safe_python_module_name).
    """
    # Replace non-alphanumeric with hyphens for folder/repo name
    folder_name = re.sub(r"[^a-zA-Z0-9_\-]", "", name.strip())
    # Replace hyphens with underscores for Python package module
    module_name = re.sub(r"[^a-zA-Z0-9_]", "_", folder_name.lower())
    # Clean leading digits for safe imports
    if module_name and module_name[0].isdigit():
        module_name = "_" + module_name

    return folder_name, module_name


def write_file(path: Path, content: str, force: bool) -> bool:
    """Safely write contents to path, preventing accidental overwrite.

    Args:
        path: Path to target file.
        content: string text payload to save.
        force: Boolean flag to allow overwrites.

    Returns:
        True if written successfully, False if skipped.
    """
    if path.exists() and not force:
        logger.warning(
            "Skipping existing file: %s (use --force to overwrite)", path.name
        )
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Created file: %s", path.relative_to(path.parent.parent))
        return True
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to write file %s: %s", path.as_posix(), err)
        return False


def bootstrap_project(
    target_dir: Path,
    proj_name: str,
    desc: str,
    ci_choice: str,
    force: bool,
) -> bool:
    """Generate all files and folder trees for Python project scaffolding.

    Args:
        target_dir: Directory where project will be created.
        proj_name: Raw name of the project.
        desc: Short project summary.
        ci_choice: 'github' or 'none'.
        force: Overwrite if files exist.

    Returns:
        True if generation completed successfully, False otherwise.
    """
    folder_name, module_name = clean_project_name(proj_name)
    if not folder_name or not module_name:
        logger.error("Invalid project name provided: '%s'", proj_name)
        return False

    project_root = target_dir / folder_name
    src_dir = project_root / "src" / module_name
    test_dir = project_root / "tests"

    logger.info(
        "Bootstrapping Python project '%s' inside %s",
        folder_name,
        project_root.as_posix(),
    )

    # Build files dictionary
    files_to_create = {
        project_root
        / "README.md": README_TEMPLATE.format(
            project_name=folder_name, description=desc
        ),
        project_root / ".gitignore": GITIGNORE_TEMPLATE,
        project_root / "pyproject.toml": PYPROJECT_TOML_TEMPLATE,
        project_root / "requirements-dev.txt": REQUIREMENTS_DEV_TEMPLATE,
        src_dir / "__init__.py": f'"""{folder_name} source package."""\n',
        src_dir / "main.py": MAIN_PY_TEMPLATE.format(project_name=folder_name),
        test_dir / "__init__.py": '"""Unit test suite."""\n',
        test_dir
        / "test_main.py": TEST_MAIN_PY_TEMPLATE.format(
            project_name=folder_name, project_module=module_name
        ),
    }

    if ci_choice == "github":
        ci_path = project_root / ".github" / "workflows" / "ci.yml"
        files_to_create[ci_path] = GITHUB_CI_TEMPLATE

    success = True
    for path, content in files_to_create.items():
        if not write_file(path, content, force):
            success = False

    return success


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Project Bootstrapper — generate clean Python structures "
            "with packaging, tests, and CI."
        )
    )

    parser.add_argument(
        "-n", "--name", required=True, help="Name of the new Python project."
    )
    parser.add_argument(
        "-d",
        "--description",
        default="A Python utility template.",
        help="Description of the project.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Target output directory (defaults to current folder).",
    )
    parser.add_argument(
        "--ci",
        choices=["github", "none"],
        default="github",
        help="CI workflow configuration to generate (default: github).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite files in directory if they already exist.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logs."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    success = bootstrap_project(
        args.output,
        args.name,
        args.description,
        args.ci,
        args.force,
    )

    if success:
        sys.stdout.write(
            f"\nProject scaffold successfully created under: {args.output.as_posix()}\n"
        )
    else:
        logger.warning("\nProject scaffolding created with errors/skipped files.")


if __name__ == "__main__":
    main()

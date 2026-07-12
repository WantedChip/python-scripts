# python-scripts

![CI](https://github.com/wantedchip/python-scripts/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)
![Status: active](https://img.shields.io/badge/status-active-brightgreen.svg)

A growing collection of standalone Python scripts, organized by category.
Each script lives in its own folder with its own short README, so you can
grab just what you need without digging through the whole repo.

See [INDEX.md](INDEX.md) for the full list of scripts.

## Structure

```
python-scripts/
├── automation/
├── checkers/
├── tools/
└── web/              # browsable/searchable catalog website for this repo
```

Each script folder looks like:

```
category-name/script-name/
├── script_name.py
├── requirements.txt   # if it has external dependencies
└── README.md          # what it does + how to run it
```

## Usage

Each script is self-contained. To run one:

```bash
cd category-name/script-name
pip install -r requirements.txt   # only if present
python script_name.py --help      # show available options and parameters
python script_name.py             # run the script
```

## Website

A browsable, searchable web catalog for this repo is available in [web/](web/). It allows you to browse by category, search scripts using multiple matching modes, preview code with full syntax highlighting, and download scripts directly. See [web/README.md](web/README.md) for instructions on how to run the site locally.

## Development

Every script is checked with `black`, `isort`, `flake8`, `pylint`, `mypy`,
`bandit`, `vulture`, and `pytest`/`pytest-cov`, run automatically on every
push across Linux, Windows, and macOS on Python 3.12–3.14. To run the same
checks locally before pushing:

```bash
pip install -r requirements-dev.txt
pre-commit install
pre-commit run --all-files
```

## License

Licensed under the [MIT License](LICENSE).
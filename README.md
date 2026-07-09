# python-scripts

![CI](https://github.com/wantedchip/python-scripts/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)
![Status: active](https://img.shields.io/badge/status-active-brightgreen.svg)

A growing collection of standalone Python scripts, organized by category.
Each script lives in its own folder with its own short README, so you can
grab just what you need without digging through the whole repo.

See [INDEX.md](INDEX.md) for the full list of scripts.

## Structure

```
python-scripts/
├── scraping/
├── automation/
├── checkers/
├── tools/
├── converters/
├── api-wrappers/
├── misc/
└── ...
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
python script_name.py
```

## License

Licensed under the [MIT License](LICENSE).

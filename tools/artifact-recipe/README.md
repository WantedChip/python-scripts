# Artifact Recipe

`artifact-recipe` provides provenance sidecars (`.recipe.json`) and an explanation CLI to answer: **"How was this file created?"** and **"Are its inputs or outputs stale?"**

## Usage

### 1. Record Provenance Sidecar

Record artifact creation details (command, working directory, input file hashes, env vars):

```bash
python main.py record --artifact output.csv --command "python build.py data.csv" --inputs data.csv --env-vars STAGE
```

To run the command and record simultaneously:
```bash
python main.py record --artifact build/bundle.js --command "npm run build" --inputs src/index.js --run
```

### 2. Explain Artifact Provenance & Staleness

Inspect provenance and check whether inputs or artifacts have changed since creation:

```bash
python main.py explain output.csv
```

### 3. Verify Directory Recipes

Verify all `.recipe.json` files in a workspace:

```bash
python main.py verify ./
```

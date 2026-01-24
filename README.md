# frog

## Pre-commit

Install the git hook once:

- Poetry (recommended):
	- `poetry install --with dev`
	- `poetry run pre-commit install`

- Or plain pip:
	- `python -m pip install pre-commit`
	- `pre-commit install`

Notes:

- On `git commit`, pre-commit runs only on staged files (the git index).
- `poetry run pre-commit run --all-files` runs only on git-tracked files.
- The trailing whitespace fixer excludes `*.csv` by default to avoid accidental data changes.

## Code Simplifier

For code quality improvement similar to GitHub Copilot's Code Simplifier agents:

```bash
# Review code for simplification opportunities
python3 tools/code_simplifier.py review [files...]
python3 tools/code_simplifier.py review --staged

# Verify changes with whitelisted commands
python3 tools/code_simplifier.py verify
```

See [doc/CODE_SIMPLIFIER.md](doc/CODE_SIMPLIFIER.md) for detailed usage.

## Line endings (LF)

This repo enforces LF via `.gitattributes`. If you need a one-time normalization (e.g. after changing `.gitattributes` or after checkout on Windows), run:

- `git add --renormalize .`

# frog

## Pre-commit

Install the git hook once:

- uv:
	- `uv sync --group dev`
	- `uv run pre-commit install`

- Or plain pip:
	- `python -m pip install pre-commit`
	- `pre-commit install`

Notes:

- On `git commit`, pre-commit runs only on staged files (the git index).
- `uv run pre-commit run --all-files` runs only on git-tracked files.
- The trailing whitespace fixer excludes `*.csv` by default to avoid accidental data changes.

## Line endings (LF)

This repo enforces LF via `.gitattributes`. If you need a one-time normalization (e.g. after changing `.gitattributes` or after checkout on Windows), run:

- `git add --renormalize .`

## Factor Research

Local factor-analysis workflows use the research dependency group:

- `uv sync --group research`

If you also need the normal dev tools in the same environment, use:

- `uv sync --group dev --group research`

Business runtime images do not include the research group.

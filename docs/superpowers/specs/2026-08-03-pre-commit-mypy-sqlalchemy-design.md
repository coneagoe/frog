# Pre-commit Mypy SQLAlchemy Environment Design

## Goal

Make the isolated pre-commit mypy hook use the same SQLAlchemy version as the project so ORM return values are type-checked consistently with `uv run mypy`.

## Change

- Keep the mypy hook pinned to `v1.20.2`.
- Add `sqlalchemy==2.0.51` to the hook's `additional_dependencies`.
- Document that changes to the SQLAlchemy version in `uv.lock` require updating the matching pre-commit dependency pin.

## Verification

- Rebuild the pre-commit cache.
- Run the mypy hook for `paper_trading/storage/repository.py`.
- Run `uv run mypy`.

## Scope

No application code, model mapping, or runtime dependency changes are included.

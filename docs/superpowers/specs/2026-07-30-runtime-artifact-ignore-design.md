# Runtime Artifact Ignore Design

## Goal

Keep local runtime artifacts, review outputs, and token-usage files out of
version control without deleting the files from developer worktrees.

## Scope

Add root-anchored `.gitignore` patterns for:

- `/docker/`
- `/logs/`
- `/.review*`
- `/token-usage-out.txt`
- `/token-usage-output.txt`

Remove already tracked paths matching those patterns from the Git index with
`git rm -r --cached`, retaining their local filesystem contents.

## Constraints

- Ignore rules apply only at the repository root and do not suppress similarly
  named source directories nested elsewhere.
- The index removal must not use plain `git rm` and must not delete local
  Docker database files, logs, review output, or token-usage files.
- No application code, Docker Compose configuration, or unrelated ignore rule
  is changed.

## Verification

Verify the paths are ignored with `git check-ignore -v`, verify they no longer
appear in `git ls-files`, and inspect `git status --short` to ensure removal is
staged while local runtime files remain present.

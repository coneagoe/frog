---
name: update_doc
description: >
  Manually inspect current repository changes, update only the affected docs,
  and summarize what changed before a later commit flow.
triggers:
  - 更新文档
  - 同步文档
  - 提交前更新文档
  - update_doc
---

# Update Docs by Current Changes

Your job is to inspect the current branch or working-tree changes, decide which
repository documents are affected, update only those documents, and then report
what changed and what did not need changes.

## Scope

- This skill is manually triggered. It does not run automatically.
- Focus on the current working tree and staged changes.
- Update only docs that are directly affected by those changes.
- Do not rewrite unrelated historical docs.
- Do not create commits automatically.

## Step 1: Understand the current state

Run these in parallel:
- `git --no-pager status --short` — see tracked and untracked changes
- `git --no-pager diff` — inspect unstaged changes
- `git --no-pager diff --cached` — inspect staged changes

Read the changed files carefully before touching any docs.

## Step 2: Decide which docs are affected

Use these rules:
- `README.md` — update when setup, usage, user-facing behavior, or architecture overview changed
- `AGENTS.md` — update when repository workflow, skill guidance, or operating instructions changed
- `CLAUDE.md` — update when repo-specific Claude workflow or coding instructions changed
- `docs/` topic docs — update when a changed subsystem already has dedicated documentation

If the correct doc target is ambiguous, stop and ask the user instead of guessing.
If no docs need changes, say that explicitly.

## Step 3: Report the result

After editing, give the user a brief summary that includes:
- which docs were updated
- why each doc changed
- which key docs were checked but did not need edits
- whether the branch is now better prepared for a later commit flow

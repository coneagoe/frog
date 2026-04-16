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

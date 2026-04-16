# Update Doc Skill Design

## Problem

The repository already uses skill-style workflow guidance, but there is no dedicated manual skill for updating repository documentation in response to the current branch or working-tree changes.

The root `SKILL.md` is commit-oriented: it groups changes into logical commits and requires checking whether repository docs need updates before committing. What is still missing is a focused skill that can be invoked directly when the user wants to sync documentation first.

## Decision

Add a manually triggered `update_doc` skill at `.agents/skills/update_doc/SKILL.md`.

This skill will be commit-linked rather than audit-driven: it will inspect the current working-tree and staged changes, determine which repository documents are affected, update only those documents, and leave the repository ready for a later commit flow.

## Design

### Scope

The first version of `update_doc` covers only documentation maintenance that is directly implied by the current branch or working-tree changes.

It should:

- inspect current changes before touching docs
- update affected repository documents
- explain which docs were updated and why
- explicitly report when key docs were checked but did not need changes

It should not:

- run a full-repository documentation audit by default
- rewrite unrelated historical docs
- create commits automatically

### Placement and trigger model

The skill lives at:

```text
.agents/skills/update_doc/SKILL.md
```

The skill is intended for explicit manual invocation. Its wording should make that clear and provide natural-language trigger examples around updating docs, syncing docs before commit, or refreshing repository instructions after code changes.

### Relationship to the existing commit skill

`update_doc` is aligned with the intent of the current root `SKILL.md`, but the responsibilities are narrower:

- the existing root skill remains focused on grouping and creating logical commits
- `update_doc` focuses only on documentation changes implied by the current code or config changes
- `update_doc` can be used before a commit flow, alongside it, or independently when the user wants docs synchronized first

This keeps documentation maintenance as a dedicated manual step instead of embedding all behavior into the commit skill.

### Main workflow

Recommended workflow:

1. read current state using `git status`, `git diff HEAD`, and `git diff --cached`
2. understand every changed file that could affect docs
3. decide which repository documents are impacted
4. read only the documents relevant to those changes
5. update the affected documents
6. summarize what changed, why it changed, and which checked docs needed no update

The skill should prefer targeted documentation updates over broad rewrites.

### Document targeting rules

Document selection should be explicit rather than ad hoc.

#### Repository-wide docs

Check and update `README.md`, `AGENTS.md`, and `CLAUDE.md` when the current changes affect:

- setup or usage
- developer workflow
- commands or tooling expectations
- architecture overview
- repository operating instructions

#### Topic docs

When current changes are concentrated in a subsystem that already has documentation under `docs/` or another established location, update that topic document instead of only editing root-level docs.

#### New documentation surfaces

If the current changes introduce a new user-visible workflow, developer rule, or operational command and no suitable document exists yet, the skill may add the minimum new documentation needed, but only when it is tightly coupled to the current changes.

### Guardrails

The skill must:

- inspect changes before editing docs
- avoid unrelated documentation cleanup
- stop and ask the user when the correct documentation destination is ambiguous
- clearly report when no documentation changes are needed

The skill must not fabricate updates simply because it was invoked.

### Output contract

The final response should stay concise and action-oriented. At minimum it should state:

- which docs were updated
- why each updated doc changed
- which important docs were checked and required no changes
- whether the repository is now better prepared for a later commit step

### Error handling

Errors should remain explicit:

- if the changed files cannot be understood well enough to decide which docs to update, the skill should ask the user instead of guessing
- if a document appears related but the intended update is ambiguous, the skill should stop for clarification
- if no relevant docs exist and creating one would be speculative, the skill should say so rather than invent scope

### Testing and validation expectations

Because this is a workflow skill rather than runtime application code, the first version should be reviewed for:

1. clear trigger wording
2. explicit workflow steps
3. correct repository-specific document rules
4. consistent boundaries between `update_doc` and the existing commit-oriented skill

## Non-goals

- automatic background documentation maintenance
- full-repository documentation audits on every invocation
- automatic git commits
- replacing the existing commit-oriented root skill


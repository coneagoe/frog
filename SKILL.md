---
name: commit
description: >
  Group uncommitted git changes into logical commits with clear messages. Use when the user asks to commit changes, split mixed work into separate commits, or organize staging before committing. Before grouping or committing, invoke the repository-local `update_doc` sub-skill so it can inspect the current changes and update any affected docs first.
---

# Commit by Topic

Your job is to analyze all uncommitted changes in the repository and commit them in logical groups, where each commit represents one coherent unit of change. Each commit message should clearly explain *why* the change was made and *what* specifically changed.

## Step 1: Understand the current state

Run these in parallel:
- `git --no-pager status` — see all tracked/untracked changes
- `git --no-pager diff` — see all unstaged changes in detail
- `git --no-pager diff --cached` — see already-staged changes
- `git --no-pager log --oneline -10` — understand the commit style of this repo

Read the output carefully. You need to understand every changed file before proceeding.

## Step 2: Invoke `update_doc` before committing

Before grouping or committing anything, invoke the repository-local `update_doc`
skill.

`update_doc` is the required documentation sub-skill for this commit workflow.
Let it inspect the current changes, update any affected docs, and report which
key docs were checked and did not need edits.

After `update_doc` completes:
- continue grouping changes by topic
- include any doc edits from `update_doc` in the same logical commit as the
  underlying code, config, or workflow change
- if `update_doc` reports that no docs needed changes, continue normally

Do not skip this step just because the user asked only to commit code.

## Step 3: Group changes by topic

Look at the files and their diffs together and identify logical themes. A "topic" is a set of changes that belong together because they:
- Implement the same feature or part of a feature
- Fix the same bug
- Refactor the same component or module
- Update the same type of thing (e.g., all config changes, all test additions, all doc updates)

Good grouping respects *intent*, not just file proximity. For example:
- A new API endpoint + its tests + its documentation = one commit
- A dependency bump + the code changes needed to make it work = one commit
- A CSS style fix and an unrelated backend bug fix = two separate commits

If all the changes clearly belong together, a single commit is fine. Don't split artificially.

When doc updates are required, include `README.md`, `CLAUDE.md`, and/or `AGENTS.md` in the same topic group as the underlying change. Only make a standalone docs-only commit when the documentation itself is the primary change.

## Step 4: For each group, draft a commit message

Commit messages must be **bilingual (中英双语)**: write each section in both Chinese and English, and always put Chinese before English. This helps the team read history in their preferred language without losing context.

The structure:

1. **Subject line** (first line): Use conventional commits format: `type(scope): description`. Keep the `type(scope):` prefix in English, then write the bilingual description in `中文 / English` order when space allows. Keep the line under 72 characters when practical.
2. **Blank line**
3. **Chinese summary** (1–2 sentences): Explain why and what in Chinese. Give the reader context — what problem does this solve, what was the old behavior?
4. **Blank line**
5. **English summary**: Same explanation in English — who reads this in a year should understand the intent without reading the code.
6. **Blank line**
7. **Change list** (bilingual bullets): Each bullet in `中文 / English` format.

**Good example:**
```
feat(auth): 新增 JWT 刷新逻辑 / add JWT refresh logic

过期 token 导致用户被静默登出。新增刷新拦截器，在收到 401 时自动请求新 token 并重试原请求。

Previously, expired tokens caused silent failures that logged users out
unexpectedly. Added a refresh interceptor that automatically requests a
new token when a 401 is received, then retries the original request.

- 新增 auth.service.ts 中的 refreshToken() 方法 / Added refreshToken() in auth.service.ts
- 新增 api.client.ts 中的 Axios 响应拦截器 / Added Axios response interceptor in api.client.ts
- Token 有效期从 1h 缩短为 15min 以减小攻击面 / Reduced token expiry from 1h to 15min
```

**Bad example:**
```
fix stuff

updated some files
```

Never add `Co-Authored-By` lines or any trailer lines attributing authorship to AI tools.

## Step 5: Commit each group

For each topic group, in a logical order (dependencies before dependents):

1. Stage only the files for this group: `git add <specific files>`
   - For partial file staging when a file has changes belonging to different topics, use `git add -p <file>`
2. Verify staged changes with `git --no-pager diff --cached` — make sure only the right files are staged
3. Commit with the message using a heredoc to preserve formatting:

```bash
git commit -m "$(cat <<'EOF'
type(scope): 中文主题 / English subject

中文说明：一两句话说清楚为什么要做这个改动，以及改了什么。

English explanation: same context in English, for readers who prefer it.

- 中文改动描述 / English description of change
- 另一个改动 / Another change
EOF
)"
```

4. Confirm the commit succeeded with `git --no-pager log --oneline -1`

Repeat for each topic group.

## Step 6: Summary

After all commits are done, show the user a brief summary:
- List each commit made (hash + subject)
- Note any files that were left uncommitted and why (e.g., intentionally excluded, ambiguous ownership)

## Important constraints

- Never use `git add .` or `git add -A` — always stage specific files to avoid accidentally committing secrets, binaries, or unrelated files
- Never skip a needed `README.md`, `CLAUDE.md`, or `AGENTS.md` update when the current changes make those docs inaccurate
- Never add `Co-Authored-By` or any other trailer lines
- Never use `--no-verify` to skip hooks — if a hook fails, fix the underlying issue
- Never amend commits that already exist
- If you're unsure which topic a file belongs to, lean toward a separate commit rather than bundling it incorrectly
- Respect `.gitignore` — don't force-add ignored files
- If there are no uncommitted changes, tell the user clearly

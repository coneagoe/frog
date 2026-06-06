# Blackroom Query Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-local `blackroom_query` skill that maps natural-language小黑屋 queries and management requests onto the existing `tools/stock_monitor_cli.py blackroom ...` commands.

**Architecture:** Keep all runtime behavior in the existing CLI and blackroom services. The new skill is documentation-only: it defines command templates, parameter clarification rules, conservative stock-code handling, and output/error-handling rules. Validate it with RED/GREEN skill tests using baseline and post-skill subagent scenarios instead of adding new application code.

**Tech Stack:** Markdown skill files under `.agents/skills/`, Poetry-run Python CLI commands, OpenCode skill discovery, subagent-based skill pressure tests. Do not create git commits unless the user explicitly requests committing.

---

## File Structure

### Create

- `.agents/skills/blackroom_query/SKILL.md`
  - New skill definition for blackroom query and management requests.
- `docs/superpowers/plans/2026-06-06-blackroom-skill.md`
  - This execution plan.

### Modify

- None required for runtime code.

### Reference Only

- `.agents/skills/stock_monitor/SKILL.md`
  - Existing style and phrasing reference.
- `tools/stock_monitor_cli.py`
  - Source of truth for supported blackroom commands and flags.
- `docs/superpowers/specs/2026-06-06-blackroom-skill-design.md`
  - Approved design spec.

---

### Task 1: Run RED baseline scenarios before creating the skill

**Files:**
- Reference: `docs/superpowers/specs/2026-06-06-blackroom-skill-design.md`
- Reference: `.agents/skills/stock_monitor/SKILL.md`

- [ ] **Step 1: Prepare two baseline pressure prompts**

Use these exact prompts for fresh subagent sessions that do **not** mention any new blackroom skill:

```text
Scenario A:
用户说：“帮我看下宁德时代和招商银行在不在小黑屋。”
要求：给出你会怎么处理，是否会直接猜股票代码，是否会直接调用 service，还是走现有 CLI。只返回你的执行方案和理由，不要修改文件。

Scenario B:
用户说：“把 600519 加进小黑屋 30 天，再看下状态。”
要求：给出你会使用的入口、命令形态、缺参处理方式。只返回执行方案和理由，不要修改文件。
```

- [ ] **Step 2: Run Scenario A without the new skill**

Dispatch a fresh read-only subagent with this exact task prompt:

```text
You are running a baseline skill-discovery test before a new skill exists. Do not edit files. Read only the minimum needed. Answer Scenario A exactly: 用户说：“帮我看下宁德时代和招商银行在不在小黑屋。” 要求：给出你会怎么处理，是否会直接猜股票代码，是否会直接调用 service，还是走现有 CLI。只返回你的执行方案和理由。
```

Expected: the agent is likely to improvise code/service usage or unclear stock-name handling. Capture the exact behavior in your session notes.

- [ ] **Step 3: Run Scenario B without the new skill**

Dispatch a fresh read-only subagent with this exact task prompt:

```text
You are running a baseline skill-discovery test before a new skill exists. Do not edit files. Read only the minimum needed. Answer Scenario B exactly: 用户说：“把 600519 加进小黑屋 30 天，再看下状态。” 要求：给出你会使用的入口、命令形态、缺参处理方式。只返回执行方案和理由。
```

Expected: the agent may not consistently choose `poetry run python tools/stock_monitor_cli.py blackroom ...` or may miss the recommended `ban`/`status` flow.

- [ ] **Step 4: Summarize RED findings**

Create a short local note in your working notes (no repo file required) listing the exact baseline failures to address in the skill. The summary must cover:

```text
- Whether the agent guessed stock codes from names
- Whether the agent bypassed the CLI and used services directly
- Whether the agent used the correct blackroom subcommands
- Whether the agent asked for missing parameters when needed
```

- [ ] **Step 5: Sanity-check CLI source of truth**

Run:

```bash
poetry run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS. This confirms the CLI behavior the skill will reference is already covered before writing the new skill.

---

### Task 2: Write the `blackroom_query` skill

**Files:**
- Create: `.agents/skills/blackroom_query/SKILL.md`
- Reference: `.agents/skills/stock_monitor/SKILL.md`
- Reference: `tools/stock_monitor_cli.py:146-220`
- Reference: `tools/stock_monitor_cli.py:350-437`
- Reference: `docs/superpowers/specs/2026-06-06-blackroom-skill-design.md`

- [ ] **Step 1: Create the skill directory**

Run:

```bash
mkdir -p .agents/skills/blackroom_query
```

Expected: the target directory exists and is ready for `SKILL.md`.

- [ ] **Step 2: Write `SKILL.md` frontmatter and overview**

Create `.agents/skills/blackroom_query/SKILL.md` with this exact starting block:

```markdown
---
name: blackroom_query
description: >
  使用现有 tools/stock_monitor_cli.py 查询和管理股票小黑屋。适用于“在不在小黑屋”、
  blackroom ban/unban/update/list/get/status/countdown/sync-shareholder-selling 等请求。
triggers:
  - 小黑屋
  - blackroom
  - 在不在小黑屋
  - 黑屋查询
  - 黑屋管理
  - blackroom ban
  - blackroom unban
  - blackroom status
---

# Blackroom Query Skill

你的任务是把用户关于“小黑屋”的自然语言请求，稳定映射为 `tools/stock_monitor_cli.py` 的 `blackroom` 子命令调用。
```

- [ ] **Step 3: Add execution constraints and unified entrypoint**

Append this section exactly:

```markdown
## 执行约束

- 必须在仓库根目录执行命令。
- Python 命令必须使用 `poetry run`。
- 统一调用入口：
  - `poetry run python tools/stock_monitor_cli.py blackroom ...`
- 当用户要求结构化输出时，附加全局 `--json`。
- 不要绕过 CLI 直接调用 `BlackroomService`。
- 用户只给股票名而未给代码时，默认先补问，不自行猜测代码。
```

- [ ] **Step 4: Add query mappings**

Append this section exactly:

```markdown
## 常见查询场景

1. 查询单只股票是否在小黑屋
   - 使用：`poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>`
   - 解释规则：返回 `data` 非空表示“在小黑屋”；返回空列表表示“不在小黑屋”。
2. 批量查询多只股票
   - 对每个股票代码分别执行：`poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>`
   - 汇总为逐只结论，不要把多个代码拼成一个 CLI 参数。
3. 查看当前活跃小黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom list --active-only`
4. 查看全部黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom list`
5. 查询单条黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom get --id <record_id>`
6. 查看黑屋状态汇总
   - `poetry run python tools/stock_monitor_cli.py blackroom status`
```

- [ ] **Step 5: Add management and operations mappings**

Append this section exactly:

```markdown
## 管理命令映射

1. 封禁股票进入小黑屋
   - 主推荐：`poetry run python tools/stock_monitor_cli.py blackroom ban --stock-code <code> --market <A|HK|ETF> --ban-days <days> [--note <text>]`
   - `add` 是兼容旧命令，不作为首选表达。
2. 更新黑屋记录
   - `poetry run python tools/stock_monitor_cli.py blackroom update --id <record_id> [--ban-days <days>] [--note <text>] [--enabled|--disabled] [--start-at <iso>] [--expire-at <iso>]`
3. 按记录 ID 删除
   - `poetry run python tools/stock_monitor_cli.py blackroom remove --id <record_id>`
4. 解除小黑屋封禁
   - 按记录 ID：`poetry run python tools/stock_monitor_cli.py blackroom unban --id <record_id>`
   - 按股票代码和市场：`poetry run python tools/stock_monitor_cli.py blackroom unban --stock-code <code> --market <A|HK|ETF>`
5. 执行剩余天数倒计时
   - `poetry run python tools/stock_monitor_cli.py blackroom countdown`
6. 同步股东减持公告进入小黑屋
   - `poetry run python tools/stock_monitor_cli.py blackroom sync-shareholder-selling --start-date <YYYYMMDD> --end-date <YYYYMMDD> [--ban-days <days>]`
```

- [ ] **Step 6: Add parameter clarification and result rules**

Append this section exactly:

```markdown
## 参数与补问规则

- 查询“是否在小黑屋”必须有股票代码；未明确市场时默认按 `A` 股处理。
- 用户只给股票名时，先补问股票代码。
- `ban` 必须有 `stock_code`、`market`、`ban_days`。
- `update` 必须有 `record_id`，且至少一个更新字段。
- `unban` 必须满足 `record_id` 或 `stock_code + market` 其中一种。
- `remove` / `get` 必须有 `record_id`。
- `sync-shareholder-selling` 必须有 `start_date`、`end_date`；`ban_days` 不提供时默认 180。

## 结果处理

- 查询类请求可以在命令输出外层补一层简洁结论，例如：`宁德时代(300750)：不在小黑屋`。
- 用户要求 JSON 时，优先返回 CLI 原始 JSON 输出。
- 管理类请求直接返回命令原始语义，不伪造附加业务字段。
- 退出码语义：
  - `0`: 成功
  - `10`: VALIDATION_ERROR
  - `11`: NOT_FOUND
  - `12`: INTERNAL_ERROR / STORAGE_ERROR / 未知内部错误
```

- [ ] **Step 7: Add concrete examples**

Append this section exactly:

```markdown
## 典型示例

```bash
# 查询 300750 是否在小黑屋
poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code 300750

# 查询当前全部活跃小黑屋记录
poetry run python tools/stock_monitor_cli.py blackroom list --active-only

# 封禁 600519 进入小黑屋 30 天
poetry run python tools/stock_monitor_cli.py blackroom ban --stock-code 600519 --market A --ban-days 30 --note "手工封禁"

# 按股票代码解禁
poetry run python tools/stock_monitor_cli.py blackroom unban --stock-code 600519 --market A

# 查询黑屋状态
poetry run python tools/stock_monitor_cli.py --json blackroom status
```
```

- [ ] **Step 8: Review the skill against the approved spec**

Read `.agents/skills/blackroom_query/SKILL.md` and confirm all of the following are present:

```text
- unified CLI entrypoint
- query-first structure
- full management command coverage
- conservative stock-name handling
- JSON/output rules
- exit-code rules
```

Expected: no gaps relative to `docs/superpowers/specs/2026-06-06-blackroom-skill-design.md`.

---

### Task 3: Run GREEN verification scenarios with the new skill present

**Files:**
- Test: `.agents/skills/blackroom_query/SKILL.md`

- [ ] **Step 1: Run Scenario A with the new skill available**

Dispatch a fresh subagent with this exact prompt:

```text
You are validating whether the new blackroom_query skill changes behavior. If a relevant skill exists, use it. Do not edit files. Answer this request: “帮我看下宁德时代和招商银行在不在小黑屋。” Explain the exact command strategy you would use, whether you would ask for stock codes, and whether you would use CLI or services directly.
```

Expected: the agent uses the new skill, refuses to guess codes by default, and routes through `poetry run python tools/stock_monitor_cli.py --json blackroom list --active-only --stock-code <code>`.

- [ ] **Step 2: Run Scenario B with the new skill available**

Dispatch a fresh subagent with this exact prompt:

```text
You are validating whether the new blackroom_query skill changes behavior. If a relevant skill exists, use it. Do not edit files. Answer this request: “把 600519 加进小黑屋 30 天，再看下状态。” Explain the exact command strategy you would use, including subcommands and output format handling.
```

Expected: the agent prefers `blackroom ban` over `add`, then `blackroom status`, both through the CLI entrypoint.

- [ ] **Step 3: Run a missing-parameter scenario**

Dispatch a fresh subagent with this exact prompt:

```text
You are validating whether the new blackroom_query skill handles missing parameters conservatively. If a relevant skill exists, use it. Do not edit files. Answer this request: “把宁德时代关进小黑屋。” Explain whether you would ask follow-up questions and why.
```

Expected: the agent asks for stock code and ban-days instead of guessing.

- [ ] **Step 4: Compare RED vs GREEN behavior**

Write a short checklist in your session notes confirming whether the new skill fixed each baseline problem:

```text
- No direct service bypass
- No implicit stock-code guessing
- Correct use of blackroom subcommands
- Correct missing-parameter clarification
```

- [ ] **Step 5: Manual discovery sanity check**

Read `.agents/skills/blackroom_query/SKILL.md` and ensure the frontmatter still includes searchable trigger terms:

```text
小黑屋
blackroom
在不在小黑屋
黑屋查询
blackroom ban
blackroom status
```

Expected: the skill remains discoverable for both Chinese and English command-like requests.

---

### Task 4: Final local verification

**Files:**
- Test: `test/tools/test_stock_monitor_cli.py`
- Verify: `.agents/skills/blackroom_query/SKILL.md`

- [ ] **Step 1: Re-run CLI tests**

Run:

```bash
poetry run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS. The new skill does not alter runtime code, so CLI tests should remain green.

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff -- .agents/skills/blackroom_query/SKILL.md docs/superpowers/specs/2026-06-06-blackroom-skill-design.md docs/superpowers/plans/2026-06-06-blackroom-skill.md
```

Expected: diff shows one new skill file plus the spec/plan docs only.

- [ ] **Step 3: Stop without committing**

Do not commit unless the user explicitly asks. Report:

```text
- skill file path
- RED/GREEN scenario outcome summary
- verification commands run and whether they passed
```

Expected: the implementation is complete, verified locally, and ready for user review or a later commit.

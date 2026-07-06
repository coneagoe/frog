# Paper Trading OpenClaw Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document and encode the OpenClaw conversation paper trading order-entry workflow so natural-language orders are confirmed in conversation before the existing CLI submits them.

**Architecture:** This is a docs/skill-only change. External conversation channels remain outside this repository; OpenClaw uses the repository's paper-trading skill to parse, clarify, confirm, and then run the existing CLI. No channel webhook service, card payload, backend API route, or parser is added.

**Tech Stack:** Markdown skill documentation, Markdown backend documentation, existing `uv run tools/paper_trading_cli.py` CLI.

## Global Constraints

- Use `uv run` for all repository Python commands.
- A-share order symbols must use 6-digit codes such as `000001`; do not add `.SH` or `.SZ` suffixes.
- Natural-language trading instructions must be structurally confirmed in the OpenClaw conversation before any order is submitted.
- Final order submission uses `uv run tools/paper_trading_cli.py order create ...`.
- Do not add channel-specific webhook server implementation, interactive card payload generation, paper trading API routes, a backend natural-language parser, or automatic matching after order entry.
- Do not automatically de-duplicate repeated confirmed order instructions unless the user explicitly asks for duplicate prevention.

---

## File Structure

- Modify `.agents/skills/paper-trading/SKILL.md`: Add a dedicated OpenClaw conversation section after `Common Mistakes` and before `Implementation Pointers`. This file owns OpenClaw runtime behavior and must state the confirmation-first order-entry rules.
- Modify `docs/paper_trading.md`: Add a short `OpenClaw Conversation Order Entry` section after the CLI wrapper section and before raw API examples. Also correct existing CLI and curl symbol examples from suffixed symbols to suffixless 6-digit codes.
- No code files or tests are created for this first version because the approved design changes behavior guidance, not backend or CLI behavior.

---

### Task 1: Update Paper Trading Skill For OpenClaw Conversation

**Files:**
- Modify: `.agents/skills/paper-trading/SKILL.md:81-99`

**Interfaces:**
- Consumes: Existing CLI command conventions in `.agents/skills/paper-trading/SKILL.md:48-75`.
- Produces: A new `## OpenClaw Conversation Order Entry` section that OpenClaw agents follow for natural-language conversation orders.

- [ ] **Step 1: Insert the OpenClaw conversation section after the Common Mistakes table**

Add this exact section between the Common Mistakes table and `## Implementation Pointers`:

````markdown
## OpenClaw Conversation Order Entry

When OpenClaw receives a natural-language paper trading order instruction through any conversation channel, treat the channel as outside this repository. Do not mention, design, or require channel-specific webhook servers, interactive card payloads, or paper trading API extensions in this repository.

For natural-language order instructions, use this confirmation-first flow:

1. Parse the user's message into a draft order.
2. Ask for any missing required field instead of guessing.
3. Send a structured confirmation message in the same conversation.
4. Submit the order only after the user gives explicit positive confirmation.
5. Report the CLI result back to the user.

Required fields before confirmation:

- `account_id`: paper trading account ID. Do not guess it.
- `symbol`: 6-digit A-share code such as `000001`. Do not add `.SH` or `.SZ`.
- `side`: `buy` or `sell`.
- `quantity`: integer quantity accepted by the CLI.
- `limit_price`: explicit limit price. Do not convert vague phrases like `市价`, `差不多`, or `按现在价格` into a price.
- `trade_date`: resolved date shown in the confirmation message. If the user says `今天`, show the actual date before submitting.

Confirmation message format:

```text
请确认录入以下模拟交易订单：

账户：1
方向：买入
代码：000001
数量：100
限价：10.00
交易日：2026-07-06

回复“确认”提交订单，回复“取消”放弃。
```

Only clear positive replies such as `确认`, `提交`, or `是，提交` authorize submission. Ambiguous replies are not confirmation; ask the user to reply with `确认` or `取消`.

If the user changes the draft before confirmation, regenerate the complete confirmation message. If the user cancels, do not run the CLI.

After confirmation, submit with the existing CLI:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-06
```

Do not automatically run matching after order entry. If the user wants matching, ask for or receive a separate matching instruction and use the existing matching command.
````

- [ ] **Step 2: Review the Overview for consistency**

Keep the current direct-order behavior in the Overview for ordinary explicit instructions, but confirm that the new OpenClaw conversation section overrides behavior for natural-language conversation orders by requiring confirmation first. No edit is needed if the file reads clearly after Step 1.

- [ ] **Step 3: Verify the skill text contains the required guardrails**

Run:

```bash
rg -n "OpenClaw Conversation Order Entry|确认|uv run tools/paper_trading_cli.py order create|Do not automatically run matching|\.SH|\.SZ" .agents/skills/paper-trading/SKILL.md
```

Expected: output includes the new section heading, the confirmation language, the order create command, the no-auto-matching rule, and the no-suffix rule.

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/paper-trading/SKILL.md
git commit -m "docs: add openclaw conversation paper trading workflow"
```

---

### Task 2: Document The OpenClaw Conversation Workflow In Paper Trading Docs

**Files:**
- Modify: `docs/paper_trading.md:72-94`

**Interfaces:**
- Consumes: Skill behavior from Task 1.
- Produces: User-facing docs for OpenClaw conversation order entry and corrected suffixless symbol examples.

- [ ] **Step 1: Correct the CLI wrapper symbol example**

Change this line in the CLI Wrapper block:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001.SZ --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-06-16
```

to:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-06-16
```

- [ ] **Step 2: Add the OpenClaw conversation section after the `--json` example**

Insert this exact section after the `uv run tools/paper_trading_cli.py --json order list --account-id 1` example and before `Use the raw API examples below...`:

````markdown
## OpenClaw Conversation Order Entry

OpenClaw can be used for conversation-based paper trading order entry. Conversation channels are outside this repository; this repository does not provide channel-specific webhook services or interactive card payloads.

For natural-language order instructions, OpenClaw should parse the message, ask for missing fields, and send a structured confirmation before submitting the order.

Example conversation:

```text
用户：账户1买入平安银行100股，10元以内

OpenClaw：请确认录入以下模拟交易订单：

账户：1
方向：买入
代码：000001
数量：100
限价：10.00
交易日：2026-07-06

回复“确认”提交订单，回复“取消”放弃。

用户：确认
```

After confirmation, OpenClaw submits the order with the existing CLI:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-06
```

Order entry does not automatically run matching. Run matching only after a separate user instruction:

```bash
uv run tools/paper_trading_cli.py matching run --trade-date 2026-07-06 --account-id 1
```
````

- [ ] **Step 3: Correct the raw API symbol example**

Change this curl body in the `Create Limit Order` section:

```bash
-d '{"symbol":"000001.SZ","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16"}'
```

to:

```bash
-d '{"symbol":"000001","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16"}'
```

- [ ] **Step 4: Verify docs contain the workflow and no suffixed sample symbols**

Run:

```bash
rg -n "OpenClaw Conversation Order Entry|000001\.SZ|000001\.SH|--symbol 000001|matching run --trade-date 2026-07-06" docs/paper_trading.md
```

Expected: output includes the new section heading, the suffixless `--symbol 000001` examples, and the matching command. It should not include `000001.SZ` or `000001.SH`.

- [ ] **Step 5: Commit**

```bash
git add docs/paper_trading.md
git commit -m "docs: document openclaw conversation paper trading entry"
```

---

### Task 3: Final Verification And Consistency Review

**Files:**
- Read: `docs/superpowers/specs/2026-07-06-paper-trading-openclaw-feishu-design.md`
- Read: `.agents/skills/paper-trading/SKILL.md`
- Read: `docs/paper_trading.md`

**Interfaces:**
- Consumes: Task 1 skill guidance and Task 2 docs.
- Produces: Verified docs-only implementation aligned with the approved design.

- [ ] **Step 1: Verify the implementation matches the approved spec**

Run:

```bash
rg -n "OpenClaw|conversation|confirmation|确认|webhook|interactive card|automatic matching|order create" docs/superpowers/specs/2026-07-06-paper-trading-openclaw-conversation-design.md .agents/skills/paper-trading/SKILL.md docs/paper_trading.md
```

Expected: output shows OpenClaw conversation wording in all three files, confirmation language in the skill and docs, and no implementation wording that claims this repo provides channel-specific webhook services or interactive card payloads.

- [ ] **Step 2: Verify no repository Python command examples violate the uv rule in touched docs**

Run:

```bash
rg -n "python tools/paper_trading_cli.py|python3 tools/paper_trading_cli.py" .agents/skills/paper-trading/SKILL.md docs/paper_trading.md
```

Expected: no matches.

- [ ] **Step 3: Verify no suffixed A-share sample remains in touched docs**

Run this docs-only check:

```bash
rg -n "000001\.(SZ|SH)" docs/paper_trading.md
```

Expected: no matches. The skill may still include suffixed examples only inside the `Using suffixed A-share symbols...` warning row.

- [ ] **Step 4: Run formatting-independent markdown sanity checks**

Run:

```bash
git diff --check
```

Expected: no trailing whitespace or whitespace errors.

- [ ] **Step 5: Commit final verification updates if needed**

If Step 1 through Step 4 required additional edits, commit them:

```bash
git add .agents/skills/paper-trading/SKILL.md docs/paper_trading.md docs/superpowers/specs/2026-07-06-paper-trading-openclaw-conversation-design.md docs/superpowers/plans/2026-07-06-paper-trading-openclaw-conversation.md
git commit -m "docs: align paper trading openclaw conversation guidance"
```

If no additional edits were needed, do not create an empty commit.

# Paper Trading OpenClaw Conversation Design

## Goal

Support paper trading order entry through OpenClaw conversation flows. OpenClaw receives natural-language trading instructions from an external conversation channel, confirms the structured order with the user in that same conversation, then operates the existing paper trading CLI after explicit confirmation.

This design does not add channel-specific webhook, card, or payload handling to the repository. The repository remains responsible for the existing paper trading CLI, API, docs, and OpenClaw skill guidance.

## Scope

In scope:

- Update `.agents/skills/paper-trading/` guidance for conversation-based OpenClaw usage.
- Document the confirmation-first workflow for natural-language order entry.
- Reuse `uv run tools/paper_trading_cli.py` for final order submission.
- Require explicit user confirmation before any order is submitted.
- Keep order submission separate from matching runs.

Out of scope:

- Channel-specific webhook server implementation.
- Channel-specific interactive card payload generation.
- New paper trading API routes.
- New natural-language parser inside the paper trading backend.
- Automatic matching after order entry.

## Architecture

The external conversation channel is only a transport for OpenClaw. OpenClaw is the actor that interprets the user message, asks follow-up questions, presents the final structured order, and runs repository commands.

```text
Conversation message
  -> OpenClaw receives the message
  -> OpenClaw applies the paper-trading skill rules
  -> OpenClaw asks for missing fields when needed
  -> OpenClaw sends a structured confirmation message in the conversation
  -> User explicitly confirms or cancels
  -> OpenClaw runs paper_trading_cli.py order create
  -> OpenClaw reports the CLI result back in the conversation
```

The existing paper trading system remains the source of truth for accounts, orders, matching, trades, positions, and cash ledger updates.

## Conversation Flow

### Successful Order Entry

Example user message:

```text
账户1买入平安银行100股，10元以内
```

OpenClaw resolves the fields and replies:

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

After the user replies `确认`, OpenClaw submits:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-06
```

Then OpenClaw reports the order result. It should not claim the order has traded unless a later matching run creates executions.

### Missing Field

If the instruction lacks a required field, OpenClaw asks for that field instead of guessing.

Example:

```text
买入平安银行100股，10元以内
```

Response:

```text
请提供 paper trading account_id。
```

### User Modification

If the user modifies the order before confirmation, OpenClaw must regenerate the full confirmation message.

Example:

```text
不对，改成200股
```

OpenClaw replies with a new complete confirmation rather than applying the old confirmation.

### Cancellation

If the user says `取消`, `先别下`, `不提交`, or equivalent cancellation wording before confirmation, OpenClaw abandons the current order-entry flow and does not run the CLI.

## Field Rules

- `account_id`: Required. OpenClaw must not guess the paper trading account.
- `symbol`: Required as a 6-digit A-share code such as `000001`. Do not add `.SH` or `.SZ` suffixes.
- `side`: Required. Must resolve to `buy` or `sell`.
- `quantity`: Required. Must be an integer accepted by the existing CLI.
- `limit_price`: Required. OpenClaw must not convert vague phrases such as `市价`, `差不多`, or `按现在价格` into a limit price.
- `trade_date`: Required in the confirmation message. OpenClaw may default to the current date when the user says `今天`, but the resolved date must be shown before confirmation.

Stock-name resolution is allowed only when confidence is high. If the symbol cannot be resolved confidently, OpenClaw must ask the user for the 6-digit code.

## Confirmation Rules

OpenClaw may submit the order only after an explicit positive confirmation, such as:

- `确认`
- `提交`
- `是，提交`

Ambiguous replies are not confirmation. OpenClaw should ask the user to reply with `确认` or `取消`.

Repeated confirmed instructions are treated as new intended orders, matching the existing paper-trading skill behavior. OpenClaw must not automatically de-duplicate repeated instructions unless the user explicitly asks for duplicate prevention.

## Execution Rules

All repository commands must use `uv run`. The order submission command is:

```bash
uv run tools/paper_trading_cli.py order create --account-id <account_id> --symbol <symbol> --side <buy|sell> --quantity <quantity> --limit-price <price> --trade-date <YYYY-MM-DD>
```

For machine-readable inspection, OpenClaw may use the existing `--json` flag:

```bash
uv run tools/paper_trading_cli.py --json order list --account-id <account_id>
```

OpenClaw should not automatically run matching after order entry. If the user wants matching, they should ask separately or confirm a separate matching command.

## Error Handling

- Missing account: Ask for `account_id`.
- Missing symbol: Ask for the 6-digit A-share code unless a high-confidence name mapping exists.
- Missing side: Ask whether the order is buy or sell.
- Missing quantity: Ask for quantity.
- Missing limit price: Ask for limit price.
- Missing or relative date: Resolve the date and show it in confirmation.
- CLI failure: Report the error summary and state that the order was not submitted successfully.
- Network/backend failure: Report the failure and do not retry automatically, to avoid duplicate orders.

## Documentation And Skill Updates

The implementation should update the paper-trading skill with a dedicated section for conversation-based OpenClaw order entry. It should also add a short documentation section to `docs/paper_trading.md` that references the OpenClaw conversation flow and the confirmation requirement.

The skill should emphasize:

- External conversation channels are not separate integration services in this repo.
- Natural-language order instructions require structured confirmation.
- Final execution uses the existing paper trading CLI.
- Matching is not automatic after order entry.

## Verification Strategy

No new backend behavior is required for the first version. Verification should focus on documentation clarity and command correctness:

- Review examples for normal buy, normal sell, missing account, missing symbol, missing price, user modification, cancellation, and CLI failure.
- Confirm the skill requires structured confirmation before `order create`.
- Confirm all commands use `uv run`.
- Confirm symbols are 6-digit codes without exchange suffixes.
- Optionally run a manual CLI flow against a local paper trading backend: account list, confirmed order create, and order list.

## Open Questions

- Whether to add a later lightweight helper for stricter schema validation if prompt-based parsing proves unstable.
- Whether to support account aliases, such as `主账户`, after the first version.
- Whether to support separate confirmed matching commands in the OpenClaw conversation workflow.

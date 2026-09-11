# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Paper-trading users who regularly review account activity, orders, executions, and portfolio analytics, while also placing simulated orders during market hours.

## Product Purpose

Paper Trading provides simulated investment accounts for creating and managing paper orders, recording executions, tracking positions and cash movements, and reviewing account performance.

## Positioning

The product connects paper account operations, order matching, historical records, and analytics in one account-scoped workspace without changing the behavior of the underlying trading system.

## Operating Context

Users select an account, review its history and analytics, filter orders and trades by a business trade date, and occasionally submit or manage paper orders. A-share and Hong Kong Connect market conventions are relevant to its data and trade dates.

## Capabilities and Constraints

- The frontend is a Next.js web application in `frontend/paper-trading`.
- Existing account, order, trade, cash flow, position import, and analytics operations remain supported.
- Frontend changes must preserve backend business behavior unless an approved API extension is necessary for pagination, account summaries, or analytics aggregation.
- Analytics activity uses order status: filled is successful and rejected is failed.
- Historical date presets and analytics period calculations use the `Asia/Shanghai` calendar.

## Brand Commitments

- The confirmed visual direction for the paper trading workspace is Ledger Desk: a calm, light, high-density review workspace with a ledger-like data hierarchy.
- Green communicates confirmed or positive states; red communicates rejected, failed, or risk states.

## Evidence on Hand

- The product's current routes, API client, types, and visual baseline are under `frontend/paper-trading`.
- The paper-trading analytics service is implemented in `paper_trading/services/analytics_service.py`.
- No external brand assets, commercial claims, or benchmark data were provided.

## Product Principles

- Account context stays visible while reviewing historical data.
- Summary metrics are trustworthy, explicitly scoped, and never inferred from a paginated result page.
- High-frequency review favors scannable tables and stable controls over decorative UI.
- Empty and unavailable states must remain distinct.

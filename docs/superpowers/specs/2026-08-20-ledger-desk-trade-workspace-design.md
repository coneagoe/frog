# Ledger Desk Trade Workspace Design

## Scope

Implement issue #77 across the Paper Trading frontend. The work covers the
Trade workspace and the shared visual system used by Accounts, Orders, Trades,
and Analytics. Existing API calls, form fields, pagination, filtering,
account selection, and order-submission behavior remain unchanged.

## Goals

- Present a light, compact, rule-based Ledger Desk visual system.
- Make Trade a focused order-entry workspace.
- Move the existing Chart symbol input from its standalone panel into the
  chart workspace toolbar.
- Preserve independent chart-symbol and order-form-symbol state.
- Keep desktop layouts dense and scannable while retaining readable narrow
  layouts, reachable controls, horizontal table scrolling, and usable
  pagination.

## Design

### Shared visual system

Update the shared stylesheet and only the page-level markup needed to apply a
consistent system: warm-white/light-grey surfaces, dark ink text, grey-green
borders, compact spacing, restrained radii no larger than 8px, and clear
focus/hover states. Green is reserved for successful or positive states; red
is reserved for failures, rejections, and risk. Existing tables remain
scrollable on narrow screens, and controls retain stable dimensions and
readable labels.

The navigation, panels, filter bars, forms, table wrappers, badges, empty
states, errors, dialogs, and pagination should share the same tokens and
density without introducing nested decorative cards or changing data flow.

### Trade workspace

Keep account selection in the Trade page. The chart section gets a compact
toolbar containing the Chart symbol label/input and any chart status or title;
the standalone Chart symbol panel is removed. `PriceChart` continues to
receive the chart symbol and render its existing empty/loading/chart states.

The order form keeps all current fields and submission behavior, including its
own Symbol state. Chart symbol and order symbol remain independent so moving
the chart control cannot change submitted payloads or introduce implicit
coupling.

On desktop, chart and order-entry areas should support quick scanning and
entry in a balanced workspace layout. On narrow screens they stack in a
predictable order, with inputs and primary actions remaining reachable without
horizontal clipping.

### Other pages

Apply the shared visual treatment to Accounts, Orders, Trades, and Analytics
while preserving their current account-scoped loading, error, empty, filter,
pagination, and mutation-refresh behavior. Avoid changes to endpoint
contracts, URL filter semantics, date presets, task boundaries, or business
logic.

## Error and responsive behavior

Existing error and empty states remain visible and distinguishable under the
light theme. Focus indicators must remain apparent against light surfaces.
Tables may overflow within their existing scroll wrappers on small screens;
page-level content and action controls must not require a desktop viewport.

## Testing and verification

- Update Trade page tests for the relocated Chart symbol control and preserve
  assertions for independent order-form behavior.
- Run the frontend lint, test, and production build commands.
- Use the repository's screenshot and UI-detector tooling when available for
  changed frontend targets, checking both desktop and mobile views.
- If screenshot or detector tooling is unavailable, report that gap while
  treating lint, tests, build, and static inspection as the required fallback.

## Out of scope

- Removing the Chart symbol input entirely.
- Synchronizing Chart symbol with the order form Symbol field.
- Changing API payloads, backend behavior, account/order/trade semantics, or
  historical filtering and pagination logic.
- Broad component-library or unrelated architectural refactoring.

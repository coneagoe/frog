# Paper Trading Trade Market Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Trade page order explicitly select and submit A-share or Hong Kong Connect market.

**Architecture:** Reuse the existing frontend `Market` union and the import modal's native selector pattern inside `OrderForm`. Make `CreateOrderInput.market` required so the client cannot silently omit it; leave the existing backend validation responsible for market/symbol compatibility and Hong Kong board-lot rules.

**Tech Stack:** Next.js, React, TypeScript, Vitest, Testing Library, ESLint.

## Global Constraints

- Always submit explicit `market`; default the Trade form to `a_share`.
- Supported values are exactly `a_share` and `hk_connect`; never infer them from the symbol.
- Display `A-share` and `Hong Kong Connect` in a labeled native selector.
- Show the 100-share lot message only for `a_share`; do not invent Hong Kong board-lot guidance.
- No backend API, order-service, metadata, CSS, or existing-order changes are needed.
- Preserve the existing Trade form account, comment, date, and required-field behavior.

---

## File Map

| File | Responsibility |
| --- | --- |
| `frontend/paper-trading/lib/types.ts` | Require `market: Market` in frontend new-order input. |
| `frontend/paper-trading/features/trading/order-form.tsx` | Hold selected market, render the selector, submit it, and make A-share quantity guidance conditional. |
| `frontend/paper-trading/features/trading/order-form.test.tsx` | Lock down default and HK submission behavior plus market-aware guidance. |

### Task 1: Add Explicit Trade Market Selection

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:121-123,205-213`
- Modify: `frontend/paper-trading/features/trading/order-form.tsx:3-45,56-108`
- Modify: `frontend/paper-trading/features/trading/order-form.test.tsx:24-183`

**Consumes:** Existing `Market = "a_share" | "hk_connect"`, existing `createOrder(accountId, input)` API client, backend validation for the selected market, and shared `.form select` styles.

**Produces:** A required `CreateOrderInput.market` and a Trade form that always sends an explicit market.

- [ ] **Step 1: Write failing Trade form tests**

Update exact existing submission expectations so A-share submissions require `market: "a_share"`. Assert the initial selector is `a_share`. Add an HK submission test using `00700`, selecting `hk_connect`, and asserting the request payload contains the exact selected market. Extend the lot-warning test so quantity `101` shows the A-share warning initially and hides after selecting HK Connect.

```tsx
it("submits the selected Hong Kong Connect market", async () => {
  render(<OrderForm accounts={accounts} selectedAccountId={1} onSubmitted={vi.fn()} />);

  await userEvent.type(screen.getByLabelText("Symbol"), "00700");
  await userEvent.selectOptions(screen.getByLabelText("Market"), "hk_connect");
  await userEvent.clear(screen.getByLabelText("Quantity"));
  await userEvent.type(screen.getByLabelText("Quantity"), "100");
  await userEvent.type(screen.getByLabelText("Limit price"), "400.00");
  await userEvent.type(screen.getByLabelText("Trade date"), "2026-07-28");
  await userEvent.click(screen.getByRole("button", { name: "Submit order" }));

  expect(createOrderMock).toHaveBeenCalledWith(1, expect.objectContaining({
    symbol: "00700",
    market: "hk_connect"
  }));
});
```

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run:

```bash
npm --prefix frontend/paper-trading test -- features/trading/order-form.test.tsx
```

Expected: FAIL because the `Market` selector does not exist and the payload omits `market`.

- [ ] **Step 3: Implement the minimal typed form change**

Add `market: Market` to `CreateOrderInput`. In `OrderForm`, import `Market`, initialize `const [market, setMarket] = useState<Market>("a_share")`, include `market` in the `createOrder` payload, and make the existing lot warning require `market === "a_share"`.

Render the selector after `Side`, preserving the existing form structure and generic select styles:

```tsx
<label>
  Market
  <select
    aria-label="Market"
    value={market}
    onChange={(event) => setMarket(event.target.value === "hk_connect" ? "hk_connect" : "a_share")}
  >
    <option value="a_share">A-share</option>
    <option value="hk_connect">Hong Kong Connect</option>
  </select>
</label>
```

Do not add CSS. Do not reset selected market after submit. Do not add market inference, frontend HK metadata requests, or backend changes.

- [ ] **Step 4: Run focused frontend test and verify it passes**

Run:

```bash
npm --prefix frontend/paper-trading test -- features/trading/order-form.test.tsx
```

Expected: PASS, including default A-share request, explicit HK request, and A-share-only guidance.

- [ ] **Step 5: Run integration verification**

Run:

```bash
npm --prefix frontend/paper-trading test
npm --prefix frontend/paper-trading run lint
npm --prefix frontend/paper-trading run build
```

Expected: all frontend tests and the production build pass. Lint must have no new errors; report any pre-existing warnings separately.

- [ ] **Step 6: Commit the focused change**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/features/trading/order-form.tsx frontend/paper-trading/features/trading/order-form.test.tsx
git commit -m "fix: select market for paper trade orders"
```

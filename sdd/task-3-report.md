status: DONE
files changed: frontend/paper-trading/app/globals.css
commits made: 8cdda7d
test command run: cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
exact test result summary: 1 test file passed, 14 tests passed, 0 failed
self-review: Updated the modal width, added the import workspace layout and typography rules, and added the mobile card fallback so the grid collapses cleanly under 760px.
concerns: None.

---

## Review Fix (Finding 1 & 2)

**status**: FIXED
**files changed**: frontend/paper-trading/app/globals.css
**commits made**: c6371bb
**test command run**: cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
**exact test result summary**: 1 test file passed, 14 tests passed, 0 failed
**self-review**:

### Finding 1 — Base `.modal` sizing scope
- Reverted `.modal` base `max-width` from `760px` → `480px` and `width` from `min(100%, calc(100vw - 32px))` → `100%`, restoring the original generic modal sizing that was changed by the initial Task 3 commit.
- Added `.modal.import-modal { max-width: min(100%, 880px); }` so the wider workspace layout is scoped exclusively to the import modal. Non-import modals (e.g. `edit-account-fees-modal.tsx`) keep the standard 480px max-width.
- The `min(100%, …)` wrapper ensures the import modal never exceeds the viewport; horizontal overflow below ~700 px viewport is handled by `.import-grid { overflow-x: auto }`.
- The 880px ceiling gives the 5-column grid (min-width 660px) ~200px of comfortable breathing room inside the modal body (40px horizontal padding + 2px border).

### Finding 2 — Desktop header/row column alignment
- Changed `.import-grid__header` from `padding: 0 2px` to `padding: 0 10px`, matching `.import-grid__row` horizontal padding.
- The grid-template and gap declarations are shared (`import-grid__header, import-grid__row`), so columns now start at the same horizontal offset in both the header and each data row. The subtle 13px offset between header label text and the input text inside row cells is expected input-padding behaviour and not a misalignment of the grid columns.
- Mobile fallback (`.import-grid__row` collapses to `1fr`; `.import-grid__header` is `display: none`) is completely untouched.

**concerns**: None.

# Duplicate Monitor Action Fix Report

## Root cause

`MonitorPage` represented pending mutations with a `Set` keyed by
`${targetId}:${action}`. Two same-target, same-action invocations therefore shared
one entry. When the first invocation completed, it removed the shared entry even
though the second request was still pending. Button disabling could not reliably
prevent the duplicate because React has not necessarily rerendered before a
second handler invocation.

## Fix

`TargetOperationGuard` records active target IDs synchronously. Every edit,
toggle, and delete handler must acquire the target before invoking its API; a
second mutation for that target is rejected immediately. The rendered busy state
is a set of active target IDs, so all mutation controls for that target remain
disabled while the operation is pending. Other target IDs can still acquire and
run concurrently.

## Red/green verification

- Red: `npm test -- features/monitor/target-operation-guard.test.ts` failed after
  temporarily removing duplicate acquisition rejection. The assertion for the
  second `begin(17)` expected `false` and received `true`.
- Green: `npm test -- features/monitor/monitor-page.test.tsx features/monitor/target-operation-guard.test.ts` passed: 2 files, 6 tests.
- Green: `npm run lint` passed.

## Commit

SHA: `ad1b5f4bdf541441be246b24e92ddb835f01a251`

## Concerns

No known concerns. The guard is per mounted monitor page, consistent with the
page-local handler lifecycle.

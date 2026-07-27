# Task 7 Recovery Documentation Report

Status: DONE

Line summary: Updated `docs/paper_trading.md` near `## Run Matching` with recovery guidance for failed snapshot generation, including `error_details` inspection, correction of market-data or holding issues, and the documented order deletion/replay/rebuild workflow. Clarified that filled orders and trades remain, no failed-account snapshot is written, and reposting the same matching request cannot regenerate it because only `ACCEPTED` orders are selected.

Commit: Pending

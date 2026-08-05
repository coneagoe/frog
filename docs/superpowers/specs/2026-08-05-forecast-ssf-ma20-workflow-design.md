# 业绩预增、社保基金与 MA20 工作流

## Problem Statement

研究者需要把公司业绩预增、风险排除、机构持仓确认和趋势确认串成一个可重复执行的 A 股监控工作流。当前系统分别具备黑屋、前十大流通股东、社保基金识别和股票监控能力，但没有一个可审计的候选池将这些能力组合起来。手工筛选会遗漏预告更新、黑屋状态变更、股东数据过期和均线条件变化，也无法可靠避免重复告警。

## Solution

新增一个由 Airflow 交易日盘后运行的候选池同步工作流。它从 Tushare 业绩预告中选择当前有效报告期内的预增公司，依次排除黑屋股票、确认最新前十大流通股东中的社保基金或基本养老保险基金持仓，然后将合格股票幂等同步为专属的日频 stock monitor 目标。监控目标在前复权日线的收盘价严格高于简单 MA20 时发送既有邮件告警。

工作流维护候选资格、筛选证据、延迟状态和人工暂停状态。它只管理带稳定 workflow 归属标记的目标，绝不修改人工创建的 monitor target。黑屋在候选同步和邮件发出前均具有最高优先级。

## User Stories

1. As an A 股研究者, I want to automatically collect current-reporting-period earnings forecasts, so that I do not manually assemble a pre-increase universe.
2. As an A 股研究者, I want only forecast records of type `预增` with `p_change_min >= 50` to qualify, so that weak or ambiguous earnings signals are excluded.
3. As an A 股研究者, I want the latest announcement for each stock and reporting period to replace older announcements, so that forecast revisions take effect promptly.
4. As an A 股研究者, I want forecast eligibility to take effect on its announcement date, so that monitoring and future backtests avoid look-ahead bias.
5. As an A 股研究者, I want the active reporting period to be determined from validated forecast data by `end_date`, so that seasonal disclosure timing does not require hard-coded calendar cutovers.
6. As an A 股研究者, I want the previous reporting-period candidate pool retained until a new reporting period synchronizes successfully, so that a delayed provider response cannot erase valid targets.
7. As an A 股研究者, I want active blackroom records to exclude a stock immediately, so that globally prohibited securities never produce workflow buy-style alerts.
8. As an A 股研究者, I want a stock to become eligible again after its blackroom record expires and all other rules pass, so that temporary restrictions do not create permanent exclusions.
9. As an A 股研究者, I want qualification to require a matching holder in the latest top-10 floating-shareholder disclosure, so that institutional confirmation is based on the latest available ownership evidence.
10. As an A 股研究者, I want the existing social-security-holder detector reused, so that `全国社保基金`, `社保基金`, and `基本养老保险基金` are interpreted consistently across the product.
11. As an A 股研究者, I want shareholder data older than two months marked deferred rather than treated as a failed screen, so that stale data cannot create new signals or incorrectly remove existing ones.
12. As an A 股研究者, I want only valid Shanghai and Shenzhen A-share common stocks to enter the workflow, so that Hong Kong, ETF, B-share, Beijing, delisted, ST, and *ST securities are outside the strategy universe.
13. As an A 股研究者, I want Tushare `ts_code` values normalized and validated before filtering, so that a provider-format issue cannot attach evidence or alerts to the wrong security.
14. As an A 股研究者, I want each eligible security synchronized to one workflow-owned daily monitor target, so that repeated runs remain idempotent and do not create duplicate alerts.
15. As an A 股研究者, I want manually managed monitor targets isolated from this workflow, so that automatic synchronization never changes personal alerts.
16. As an A 股研究者, I want to pause a workflow-owned target manually, so that qualification evidence continues to update without automatically re-enabling monitoring.
17. As an A 股研究者, I want a qualifying stock to alert when its finalized daily close is above MA20, so that the signal confirms a continuing positive trend rather than requiring an intraday cross.
18. As an A 股研究者, I want the MA20 calculation and close to use the same front-adjusted daily-price series, so that the technical comparison is internally consistent.
19. As an A 股研究者, I want insufficient daily bars, a trading-day mismatch, or a halted security to preserve the monitor state, so that missing data does not reset or fabricate a signal.
20. As an A 股研究者, I want a new or requalified target to alert once if it is already above MA20, so that a newly valid opportunity is visible.
21. As an A 股研究者, I want continuously eligible targets to retain their edge-trigger state, so that metadata refreshes do not repeat alerts.
22. As an A 股研究者, I want an email-time blackroom check, so that a restriction added after the daily synchronization still blocks the alert.
23. As an A 股研究者, I want every candidate decision to retain forecast, shareholder, blackroom, and timing evidence, so that I can audit why a target was enabled, deferred, disabled, or paused.
24. As an A 股研究者, I want successful empty results distinguished from provider or schema failure, so that an empty candidate pool is not confused with a broken data pipeline.
25. As an operator, I want a failed system-wide synchronization to leave the last successful target state unchanged, so that partial provider data cannot cause mass target disablement.
26. As an operator, I want per-stock shareholder failures to defer only the affected stock, so that other complete candidates can still synchronize.
27. As an operator, I want a structured synchronization summary with stage counts and state transitions, so that DAG logs and operations can explain the run outcome.
28. As an operator, I want the workflow to run after final daily-bar availability and before daily monitor evaluation, so that the signal uses complete information in a deterministic order.
29. As an operator, I want retries and reruns to be transactionally idempotent, so that duplicate candidate records, targets, and alerts are not introduced.
30. As a strategy user, I want this workflow to remain a research and monitoring signal rather than an automatic execution instruction, so that investment decisions remain explicitly controlled.

## Implementation Decisions

- Add a forecast ingestion and persistence capability using the Tushare `forecast` dataset. Persist the fields necessary to identify the A-share security, reporting period, announcement date, forecast type, and growth interval. Provider errors, absent mandatory fields, malformed values, and unverifiable reporting-period coverage are systemic synchronization failures.
- The active reporting period is selected from valid forecast records using the greatest `end_date` not later than the synchronization date. The workflow promotes a new active period only after the complete forecast data set is validated and synchronization succeeds.
- A forecast candidate is eligible only if it is a valid `.SH` or `.SZ` Tushare code, belongs to the supported non-ST A-share universe, has `type` exactly `预增`, and has a numeric `p_change_min` of at least 50. `略增`, `扭亏`, `续盈`, `预减`, withdrawn, missing, or malformed forecasts are ineligible.
- For each `(stock_code, end_date)`, select the greatest `ann_date`. When provider data has duplicate records with identical announcement dates, use a deterministic final provider order and log the conflict.
- Qualification is effective from the forecast announcement date. A later same-period forecast correction immediately replaces the former result on the next successful synchronization.
- Use BlackroomService candidate filtering during synchronization. A valid blackroom record is a hard exclusion and disables the workflow-owned target, even if the remaining inputs qualify. On expiry, the stock can return through a later successful full screen.
- Query the latest announcement date in the existing top-10 floating-shareholder data for each candidate. Reuse the existing `is_social_security_holder` detector without a separate keyword list. At least one matching holder is required.
- If the latest top-10 floating-shareholder announcement is more than two calendar months before the synchronization date, or shareholder data is absent, mark the stock `deferred`. Deferred records cannot create or recover targets and cannot automatically disable a previously enabled workflow-owned target.
- Add a workflow candidate-state store with stable per-stock identity, active reporting period, qualification state (`eligible`, `ineligible`, `deferred`, `blackroom`, `paused`, `delisted_or_unlisted`), evidence snapshot, timestamps, and the associated monitor-target identity. Evidence includes the selected forecast, shareholder match and announcement date, blackroom result, and state-transition reason.
- Define the stable monitor-condition ownership marker as `workflow: "forecast_ssf_ma20"`. Each `(stock_code, market, workflow)` owns at most one monitor target. Synchronization only creates, updates, enables, or disables that owned record. It never inspects or alters unmarked manual targets.
- Preserve workflow targets when they become ineligible or blackroom-blocked by disabling rather than deleting them. Requalification reuses the same target. Add a workflow-specific manual pause state; paused targets retain current evidence but synchronization cannot re-enable them until explicitly resumed.
- Add a sustained price-versus-moving-average condition represented by `type: "price_vs_ma"`, `direction: "above"`, and `period: 20`. This is distinct from the existing cross condition: it is true whenever the close is strictly above the simple MA20.
- Evaluate this workflow only in the daily monitor after final daily data is available. Use a front-adjusted A-share daily series for both close and MA20. The target stock's newest bar must match the evaluated trading day; otherwise evaluation is insufficient data and leaves the prior edge-trigger state unchanged.
- New and requalified enabled workflow targets start with a false edge-trigger state, allowing an alert on their first successful `close > MA20` evaluation. Continuing qualified targets retain their state across candidate metadata refreshes. Falling to or below MA20 auto-resets the state, and a subsequent strict move above can alert again.
- Before sending an alert for a workflow-owned target, recheck BlackroomService. If banned, do not send; disable the target and write the blackroom reason to candidate state.
- The workflow DAG is an additive daily, post-close orchestration path with a single active run. Its order is verified daily-bar availability, candidate synchronization, and existing daily monitor evaluation. It does not alter the schedules, dependencies, retries, task boundaries, or SLAs of existing DAGs.
- Complete all planned candidate-state and target changes atomically after a successfully validated run. A systemic failure causes DAG failure and performs no candidate or target state changes. Per-stock shareholder failures are deferred and included in the summary.
- Produce a structured synchronization summary containing forecast input count, threshold-qualified count, blackroom exclusions, social-security-holder passes, deferred records, created/recovered/continuing/disabled/paused target counts, and representative error details. A successful zero-result run is not an error and does not generate a selection email.
- Enrich technical trigger alerts from the candidate-state evidence with the reporting period, forecast lower growth bound, forecast announcement date, matching holder name, and shareholder announcement date. Candidate synchronization itself does not send selection emails.

## Testing Decisions

- Treat externally visible candidate state, workflow-owned monitor-target state, and alert delivery behavior as the contract. Do not test private helper arrangements or internal query construction when the same outcome can be verified through a service boundary.
- Use the candidate-pool synchronization service as the main high-level test seam. Inject forecast, supported-universe, blackroom, shareholder, candidate-state, and target-storage collaborators, then assert eligibility decisions, evidence, deferred protection, pause behavior, and idempotent target transitions.
- Add isolated monitor-condition tests at the existing condition-evaluation seam for `price_vs_ma`: strict comparison semantics, exactly-equal close, insufficient bars, missing values, and consistency with daily state reset behavior.
- Add monitor-runner tests for workflow ownership filtering, current-trading-day bar validation, post-sync edge-trigger behavior, and the pre-email blackroom recheck.
- Add storage contract tests for forecast persistence, latest-record selection, candidate state upsert/history, target ownership uniqueness, and transaction behavior.
- Add DAG callable tests that verify the additive post-close ordering and that a systemic source failure writes neither candidate state nor target mutations.
- Reuse the existing fake-storage, MagicMock-based monitor service and runner test style; mock Tushare and all external providers. Do not use live provider calls in tests.
- Test representative forecast revisions, stale shareholder data, fresh-data recovery, blackroom addition and expiry, ST filtering, unavailable shareholder data, target pause/resume, delisted-or-unlisted disablement, rerun idempotency, and email-send failure without marking an alert as delivered.

## Out of Scope

- Automated order placement, position sizing, trading decisions, and paper-trading integration.
- Hong Kong shares, ETFs, indexes, B shares, Beijing Exchange securities, and other non-supported markets.
- ST and *ST securities.
- Treating `略增`, `扭亏`, `续盈`, or non-`预增` forecast types as equivalent to the approved earnings signal.
- Changing existing DAG schedules, dependencies, retry policies, task boundaries, or SLAs.
- Replacing the existing social-security-holder detector or redesigning the wider stock monitor condition system beyond the sustained MA comparison required here.
- Historical strategy performance claims or a backtest implementation. Any future backtest must honor announcement-date signal availability.

## Further Notes

- The blackroom is the highest-priority exclusion at both candidate synchronization and alert delivery time.
- A two-month shareholder freshness limit applies to data age, not the weekly ingestion job's normal synchronization lag.
- A successful current-period synchronization is required before older-period workflow targets may be retired for period rollover.
- Existing active user changes in the worktree are unrelated and must not be included in the feature implementation or PRD commit.

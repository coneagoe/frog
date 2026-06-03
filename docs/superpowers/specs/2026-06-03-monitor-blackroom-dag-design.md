# Monitor Blackroom DAG Design

## Goal

Add the shareholder-selling blackroom sync and blackroom countdown services to the existing daily monitor DAG.

## Approach

Use `dags/monitor_stock_daily.py` as the integration point because it already owns the daily monitoring schedule after market close. Add two Airflow `PythonOperator` tasks that call the existing service classes directly:

1. `sync_shareholder_selling_blackroom` calls `ShareholderSellingPunishmentService.sync(...)`.
2. `countdown_blackroom_records` calls `BlackroomCountdownService.run()`.

The shareholder-selling sync must run every scheduled weekday regardless of whether A-share trading is open. Therefore it must not be downstream of `run_daily_monitor`, because that task raises `AirflowSkipException` on non-trading days. The countdown task should run after the sync so newly added blackroom records have their remaining-day values updated in the same DAG run.

## Task Flow

The DAG should use this dependency shape:

```text
sync_shareholder_selling_blackroom >> countdown_blackroom_records
run_daily_monitor                 >> countdown_blackroom_records
```

This lets shareholder-selling sync execute independently of the trading-day-gated daily stock monitor while still keeping countdown after both upstream tasks when both run.

## Dates and Configuration

The sync task should derive `start_date` and `end_date` from the Airflow logical date and format them as `YYYYMMDD`. `ban_days` stays at the CLI default of `180`.

## Error Handling

Both new task callables should inspect the service result dictionary. If `success` is false, raise `Exception` with the service `code` and `message` so Airflow marks the task failed and applies the existing DAG retry and alert defaults.

## Testing

Add DAG-level unit tests that avoid importing real Airflow by stubbing the required Airflow modules. Tests should verify:

- shareholder-selling sync uses the logical date and ban_days `180`;
- sync failure raises an exception;
- countdown calls `BlackroomCountdownService.run()` and returns a completion message;
- countdown failure raises an exception;
- source-level DAG dependencies do not place shareholder-selling sync downstream of `run_daily_monitor`.

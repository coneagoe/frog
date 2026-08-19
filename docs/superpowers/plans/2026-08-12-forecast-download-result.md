# Forecast Download Result Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return a structured, immutable result for every one-date forecast download outcome.

**Architecture:** Add `ForecastDownloadResult` at the download-manager boundary and change `DownloadManager.download_forecast` to return it for both successful and unsuccessful execution. The method retains the existing downloader, storage, empty-frame, and exception-logging behavior; only its observable return contract changes. Focused manager tests mock the downloader and storage seams, so they verify the contract without a TuShare call.

**Tech Stack:** Python 3.11+, `dataclasses`, pandas, pytest, unittest.mock, uv.

## Global Constraints

- Change only `download/download_manager.py` and `test/download/test_download_manager.py`; do not add DAGs, backfill commands, schema changes, or downstream callers.
- Keep the existing TuShare forecast normalization and `save_forecasts` upsert behavior unchanged.
- A returned empty DataFrame is a successful outcome when `save_forecasts` returns `True`.
- `ForecastDownloadResult` fields are exactly `announcement_date: str`, `source_rows: int`, `a_share_rows: int`, and `saved: bool`.
- Every invocation returns `ForecastDownloadResult`; unexpected provider or persistence exceptions are logged using the existing Chinese error message and return zero counts with `saved=False`.
- Use `uv run` for all Python and pytest commands.

---

### Task 1: Define and Exercise the Forecast Result Contract

**Files:**
- Modify: `download/download_manager.py:1-3,144-153`
- Modify: `test/download/test_download_manager.py:84-95`

**Interfaces:**
- Consumes: `Downloader.dl_forecast(*, ann_date: str) -> pd.DataFrame | None` and `get_storage().save_forecasts(df: pd.DataFrame) -> bool`.
- Produces: `@dataclass(frozen=True) class ForecastDownloadResult` with `announcement_date: str`, `source_rows: int`, `a_share_rows: int`, and `saved: bool`.
- Produces: `DownloadManager.download_forecast(self, ann_date: str) -> ForecastDownloadResult`.

- [ ] **Step 1: Replace the existing forecast boolean test with failing result-contract tests**

  In `test/download/test_download_manager.py`, replace `test_download_forecast_saves_provider_result` and add the following focused cases in `TestDownloadManager`:

  ```python
  def test_download_forecast_reports_saved_rows(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      forecast = pd.DataFrame({"股票代码": ["600001", "000001"]})
      downloader.dl_forecast.return_value = forecast
      storage.save_forecasts.return_value = True

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 2, 2, True)
      downloader.dl_forecast.assert_called_once_with(ann_date="2025-01-01")
      storage.save_forecasts.assert_called_once_with(forecast)

  def test_download_forecast_reports_saved_empty_result(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      forecast = pd.DataFrame()
      downloader.dl_forecast.return_value = forecast
      storage.save_forecasts.return_value = True

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 0, 0, True)
      storage.save_forecasts.assert_called_once_with(forecast)

  def test_download_forecast_reports_unsaved_provider_none(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      downloader.dl_forecast.return_value = None

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 0, 0, False)
      storage.save_forecasts.assert_not_called()

  def test_download_forecast_reports_unsaved_provider_error(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      downloader.dl_forecast.side_effect = RuntimeError("provider unavailable")

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 0, 0, False)
      storage.save_forecasts.assert_not_called()

  def test_download_forecast_reports_unsaved_persistence_result(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      forecast = pd.DataFrame({"股票代码": ["600001"]})
      downloader.dl_forecast.return_value = forecast
      storage.save_forecasts.return_value = False

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 1, 1, False)
      storage.save_forecasts.assert_called_once_with(forecast)

  def test_download_forecast_reports_unsaved_persistence_error(self, monkeypatch):
      manager, storage, downloader = _make_manager(monkeypatch)
      downloader.dl_forecast.return_value = pd.DataFrame({"股票代码": ["600001"]})
      storage.save_forecasts.side_effect = RuntimeError("database unavailable")

      result = manager.download_forecast(ann_date="2025-01-01")

      assert result == dm.ForecastDownloadResult("2025-01-01", 0, 0, False)
  ```

- [ ] **Step 2: Run the focused contract tests and confirm they fail before implementation**

  Run:

  ```bash
  uv run pytest test/download/test_download_manager.py::TestDownloadManager -k download_forecast -v
  ```

  Expected: FAIL because `ForecastDownloadResult` does not exist and `download_forecast` still returns a boolean.

- [ ] **Step 3: Implement the immutable result and return it from every path**

  In `download/download_manager.py`, import `dataclass` and define the result above `DownloadManager`:

  ```python
  @dataclass(frozen=True)
  class ForecastDownloadResult:
      announcement_date: str
      source_rows: int
      a_share_rows: int
      saved: bool
  ```

  Replace the method with this implementation:

  ```python
  def download_forecast(self, ann_date: str) -> ForecastDownloadResult:
      try:
          df = self.downloader.dl_forecast(ann_date=ann_date)
          if df is None:
              raise ValueError("forecast provider returned None")
          source_rows = len(df)
          saved = get_storage().save_forecasts(df)
          return ForecastDownloadResult(ann_date, source_rows, len(df), saved)
      except Exception as exc:
          logging.error("下载业绩预告数据失败: %s", exc)
          return ForecastDownloadResult(ann_date, 0, 0, False)
  ```

  This preserves the existing storage call for empty DataFrames. `a_share_rows`
  is `len(df)` because `dl_forecast` already returns normalized A-share rows.
  Do not introduce a new normalization layer or alter any other manager method.

- [ ] **Step 4: Run the focused forecast result tests and confirm they pass**

  Run:

  ```bash
  uv run pytest test/download/test_download_manager.py::TestDownloadManager -k download_forecast -v
  ```

  Expected: all six forecast-result tests PASS.

- [ ] **Step 5: Run formatting, linting, and the full manager test module**

  Run:

  ```bash
  uv run ruff format --check download/download_manager.py test/download/test_download_manager.py
  uv run ruff check download/download_manager.py test/download/test_download_manager.py
  uv run pytest test/download/test_download_manager.py
  ```

  Expected: each command exits with status 0.

- [ ] **Step 6: Review the scoped diff and commit the implementation**

  Run:

  ```bash
  git diff --check
  git diff -- download/download_manager.py test/download/test_download_manager.py
  git status --short
  ```

  Confirm only the two task files are staged, then commit:

  ```bash
  git add download/download_manager.py test/download/test_download_manager.py
  git commit -m "feat: add forecast download result"
  ```

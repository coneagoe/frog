# Repair Historical ETF Paper Market Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dry-run-first authenticated API and CLI operation that corrects catalogue-backed historical A-share Paper Trading orders to ETF and independently rebuilds every affected account.

**Architecture:** A dedicated `HistoricalEtfMarketRepairService` queries candidates through an `ETFBasic` catalogue join and returns immutable result records. In apply mode it uses a supplied session factory to create one transaction per account, locks the account, changes its remaining candidates to `Market.ETF`, and calls the existing `OrderDeleteService.rebuild_account_from`; API, schemas, and CLI only expose this service contract.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL/SQLite, pytest, Ruff, mypy, uv.

## Global Constraints

- Candidate selection is exclusively a `PaperOrder.market == "a_share"` and `ETFBasic` catalogue join; no caller-provided symbols, prefix heuristic, or ETF eligibility filter.
- Dry run is the default for the API and CLI and must make no database writes.
- Apply mode must isolate each account in its own transaction and lock the account before changing orders or replay state.
- A failed account repair rolls back its market corrections and derived replay state without undoing successfully committed accounts.
- Reuse `OrderDeleteService.rebuild_account_from`; do not change delayed daily-bar rebuild behavior.
- Preserve historical A-share missing-date diagnostics; an available raw ETF daily bar must not create a new ETF missing-date diagnostic during replay.
- Preserve existing ETF fee, tick, lot, T+1, settlement, matching, valuation, snapshot, and market-qualified identity behavior.
- API endpoint: `POST /paper/repairs/etf-markets`, body `{ "apply": false }` by default.
- CLI command: `repair etf-markets [--apply]`; `--json` follows existing CLI output conventions.
- Use `uv run` for Python commands and `tools/run_tests.sh` for PostgreSQL-integrated coverage.
- Do not change database schemas, DAG scheduling, dependencies, retries, task boundaries, or SLA.
- Do not stage or commit implementation or documentation changes unless the user explicitly requests a commit.

---

## File Structure

- `paper_trading/services/historical_etf_market_repair_service.py`: Candidate discovery, result dataclasses, per-account transaction isolation, market correction, and replay orchestration.
- `paper_trading/storage/repository.py`: Read and update helpers for the exact catalogue-backed historical-order repair query.
- `paper_trading/schemas/repairs.py`: Pydantic request and response schemas for the repair API contract.
- `paper_trading/api/deps.py`: A lightweight session-factory dependency derived from the normal Paper Trading database configuration.
- `paper_trading/api/routers/repairs.py`: Authenticated route that invokes dry-run or apply repair and serializes outcomes.
- `paper_trading/api/app.py`: Registers the repair router.
- `tools/paper_trading_cli.py`: HTTP client method, parser branch, command handler, usage text, and subcommand discovery for `repair etf-markets`.
- `test/paper_trading/services/test_historical_etf_market_repair_service.py`: Candidate, dry-run, replay, locking, independent transaction, failure, and no-op tests.
- `test/paper_trading/api/test_repairs_api.py`: Endpoint authentication, request default, apply behavior, and response transport tests.
- `test/tools/test_paper_trading_cli.py`: CLI parser, apply forwarding, JSON, and client request tests.

### Task 1: Add Repository Repair Query And Update Helpers

**Files:**
- Modify: `paper_trading/storage/repository.py:1-11, 540-578`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Consumes: `PaperOrder`, `Market`, `ETFBasic` from `storage.model.etf_basic`.
- Produces: `PaperTradingRepository.list_catalogue_etf_a_share_orders(account_id: int | None = None) -> list[PaperOrder]` and `PaperTradingRepository.update_orders_market(order_ids: list[int], market: Market) -> int`.

- [ ] **Step 1: Add failing candidate-query tests**

  In `test/paper_trading/storage/test_repository.py`, import `ETFBasic` and
  create an ETF catalogue row plus four orders: a catalogue-backed A-share ETF,
  a catalogue-backed ETF order, a non-catalogue A-share order, and a
  non-six-digit A-share order. Assert the query returns only the first order
  and supports account filtering:

  ```python
  candidates = repo.list_catalogue_etf_a_share_orders()
  assert [order.id for order in candidates] == [a_share_etf.id]
  assert repo.list_catalogue_etf_a_share_orders(other_account.id) == []
  ```

- [ ] **Step 2: Add a failing targeted-update test**

  Create one A-share and one ETF order. Update only the A-share order ID and
  assert that the helper returns `1`, persists `etf` on the targeted order, and
  does not modify the other order:

  ```python
  changed = repo.update_orders_market([a_share_order.id], Market.ETF)
  assert changed == 1
  assert repo.get_order(a_share_order.id).market == Market.ETF.value
  assert repo.get_order(existing_etf_order.id).market == Market.ETF.value
  ```

- [ ] **Step 3: Run the new repository tests and verify failure**

  Run: `uv run pytest test/paper_trading/storage/test_repository.py -k "catalogue_etf_a_share or update_orders_market" -v`

  Expected: FAIL because neither repository method exists.

- [ ] **Step 4: Implement the catalogue join helper**

  Import `ETFBasic` and add this repository method near `list_orders`:

  ```python
  def list_catalogue_etf_a_share_orders(self, account_id: int | None = None) -> list[PaperOrder]:
      query = (
          self.session.query(PaperOrder)
          .join(ETFBasic, PaperOrder.symbol == ETFBasic.基金代码)
          .filter(
              PaperOrder.market == Market.A_SHARE.value,
              func.length(PaperOrder.symbol) == 6,
          )
      )
      if account_id is not None:
          query = query.filter(PaperOrder.account_id == account_id)
      return list(query.order_by(PaperOrder.account_id.asc(), PaperOrder.trade_date.asc(), PaperOrder.id.asc()).all())
  ```

  The join is the catalogue test and `ETFBasic.基金代码` is the authoritative
  six-digit catalogue key. The length predicate prevents malformed order values
  from matching on databases that do not enforce `String(6)` length. Do not add
  a backend-specific regular expression predicate. Keep `func` imported from
  SQLAlchemy, as it already is in this repository module.

- [ ] **Step 5: Implement the targeted market update helper**

  Add this method immediately after the candidate query:

  ```python
  def update_orders_market(self, order_ids: list[int], market: Market) -> int:
      if not order_ids:
          return 0
      changed = (
          self.session.query(PaperOrder)
          .filter(PaperOrder.id.in_(order_ids))
          .update({PaperOrder.market: market.value}, synchronize_session=False)
      )
      self.session.flush()
      return int(changed)
  ```

- [ ] **Step 6: Run focused repository coverage**

  Run: `uv run pytest test/paper_trading/storage/test_repository.py -k "catalogue_etf_a_share or update_orders_market" -v`

  Expected: PASS. The query excludes already-ETF, non-catalogue, and malformed
  symbols, and the update is scoped to supplied IDs.

- [ ] **Step 7: Check task scope**

  Run: `git diff --check -- paper_trading/storage/repository.py test/paper_trading/storage/test_repository.py`

  Expected: PASS with no whitespace errors. Leave changes unstaged.

### Task 2: Implement Independent Historical ETF Repair Service

**Files:**
- Create: `paper_trading/services/historical_etf_market_repair_service.py`
- Test: `test/paper_trading/services/test_historical_etf_market_repair_service.py`

**Interfaces:**
- Consumes: `PaperTradingRepository.list_catalogue_etf_a_share_orders`, `PaperTradingRepository.update_orders_market`, `OrderDeleteService.rebuild_account_from`, `MarketDataProvider`, and a `Callable[[], Session]` session factory.
- Produces: `RepairCandidate`, `RepairedAccount`, `FailedAccount`, `HistoricalEtfMarketRepairResult`, and `HistoricalEtfMarketRepairService.run(apply: bool = False) -> HistoricalEtfMarketRepairResult`.

- [ ] **Step 1: Create service test fixtures and failing dry-run coverage**

  Create `test/paper_trading/services/test_historical_etf_market_repair_service.py`.
  Build a file-backed SQLite engine, create `Base.metadata`, and use a
  `sessionmaker` as the service's factory so each account can use a separate
  session. Seed an `ETFBasic("518880")`, an A-share order for it, and a
  non-catalogue A-share order. Commit the seed session before calling the
  service.

  Add this test:

  ```python
  def test_dry_run_reports_catalogue_backed_a_share_orders_without_writes(tmp_path):
      session_factory, seed_session, account, candidate, untouched = _seed_candidates(tmp_path)
      result = HistoricalEtfMarketRepairService(
          session_factory, FakeMarketDataProvider()
      ).run()

      assert result.dry_run is True
      assert result.candidates == [
          RepairCandidate(account.id, candidate.id, "518880", date(2026, 8, 7))
      ]
      assert result.corrected_orders == []
      assert result.repaired_accounts == []
      assert result.skipped_accounts == []
      assert result.failed_accounts == []
      seed_session.expire_all()
      assert seed_session.get(PaperOrder, candidate.id).market == Market.A_SHARE.value
      assert seed_session.get(PaperOrder, untouched.id).market == Market.A_SHARE.value
  ```

- [ ] **Step 2: Run the dry-run test and verify failure**

  Run: `uv run pytest test/paper_trading/services/test_historical_etf_market_repair_service.py::test_dry_run_reports_catalogue_backed_a_share_orders_without_writes -v`

  Expected: FAIL because the service module does not exist.

- [ ] **Step 3: Define immutable service result records and dry-run discovery**

  Create `paper_trading/services/historical_etf_market_repair_service.py` with
  frozen dataclasses and a service constructor:

  ```python
  @dataclass(frozen=True)
  class RepairCandidate:
      account_id: int
      order_id: int
      symbol: str
      trade_date: date

  @dataclass(frozen=True)
  class RepairedAccount:
      account_id: int
      order_ids: list[int]
      replay_start_date: date

  @dataclass(frozen=True)
  class FailedAccount:
      account_id: int
      error: str

  @dataclass(frozen=True)
  class HistoricalEtfMarketRepairResult:
      dry_run: bool
      candidates: list[RepairCandidate]
      corrected_orders: list[RepairCandidate]
      repaired_accounts: list[RepairedAccount]
      skipped_accounts: list[int]
      failed_accounts: list[FailedAccount]

  class HistoricalEtfMarketRepairService:
      def __init__(self, session_factory: Callable[[], Session], market_data: MarketDataProvider):
          self._session_factory = session_factory
          self._market_data = market_data
  ```

  In `run`, open one discovery session with a context manager, convert
  `list_catalogue_etf_a_share_orders()` to `RepairCandidate` records, and
  return empty apply-outcome lists when `apply` is false. The discovery session
  does not commit or flush.

- [ ] **Step 4: Run the dry-run test and verify success**

  Run: `uv run pytest test/paper_trading/services/test_historical_etf_market_repair_service.py::test_dry_run_reports_catalogue_backed_a_share_orders_without_writes -v`

  Expected: PASS with no changes to candidate markets or derived state.

- [ ] **Step 5: Add failing successful-apply and full-derived-state coverage**

  Seed account 6-like data with an A-share `518880` buy order dated
  `2026-08-07`, a raw ETF bar with low `8.774`, high `8.892`, close `8.892`, and
  a retained A-share `missing_exact_date` diagnostic. Use an ETF-aware market
  data fake that asserts `market == "etf"` for `518880` and returns the raw bar.

  Write a test asserting:

  ```python
  result = service.run(apply=True)
  assert result.corrected_orders == [RepairCandidate(account.id, order.id, "518880", trade_date)]
  assert result.repaired_accounts == [RepairedAccount(account.id, [order.id], trade_date)]
  assert result.failed_accounts == []
  assert persisted_order.market == Market.ETF.value
  assert persisted_order.status == OrderStatus.FILLED.value
  assert all(item.market == Market.ETF.value for item in repo.list_trades(account.id))
  assert repo.get_position(account.id, Market.ETF, "518880").total_quantity == 100
  assert all(item.market == Market.ETF.value for item in repo.get_lots(account.id, Market.ETF, "518880"))
  assert repo.list_cash_ledger(account.id)
  assert repo.list_round_trips(account.id)
  assert repo.list_snapshots(account.id)
  assert repo.list_matching_runs()
  assert repo.get_valuation_gap(account.id, trade_date) is None
  assert any(item.market == Market.A_SHARE.value and item.stock_id == "518880" for item in repo.list_daily_bar_diagnostics())
  assert not any(item.market == Market.ETF.value and item.stock_id == "518880" for item in repo.list_daily_bar_diagnostics())
  assert all(item.market == Market.ETF.value for item in repo.list_trade_validity_checks(order.id))
  ```

  Use `repo.list_round_trips`, `repo.list_matching_runs`, and standard list
  helpers rather than private persistence internals.

- [ ] **Step 6: Run the apply test and verify failure**

  Run: `uv run pytest test/paper_trading/services/test_historical_etf_market_repair_service.py -k "applies_catalogue_etf or derived_state" -v`

  Expected: FAIL because apply processing is not implemented.

- [ ] **Step 7: Implement per-account apply behavior**

  Extend `run` to group discovery candidates by account ID, sorted by account ID.
  For each ID, call a private `_repair_account(account_id)` that opens its own
  session. It catches exceptions inside the context manager, rolls back that
  session, and returns a `FailedAccount`; `run` continues with later accounts.
  The successful path must use this order:

  ```python
  with self._session_factory() as session:
      repo = PaperTradingRepository(session)
      repo.lock_account(account_id)
      orders = repo.list_catalogue_etf_a_share_orders(account_id)
      if not orders:
          session.rollback()
          return None
      order_ids = [order.id for order in orders]
      start_date = min(order.trade_date for order in orders)
      repo.update_orders_market(order_ids, Market.ETF)
      OrderDeleteService(repo, self._market_data).rebuild_account_from(account_id, start_date, order_ids)
      session.commit()
      return RepairedAccount(account_id, order_ids, start_date)
  ```

  `run(apply=True)` appends the discovery records corresponding to each
  committed account to `corrected_orders`; it appends the account ID to
  `skipped_accounts` if `_repair_account` returns `None`; and appends a returned
  `FailedAccount` without interrupting the remaining account loop. Do not return
  tracebacks or exception reprs from the service result.

- [ ] **Step 8: Run successful-apply coverage**

  Run: `uv run pytest test/paper_trading/services/test_historical_etf_market_repair_service.py -k "applies_catalogue_etf or derived_state" -v`

  Expected: PASS. Replay fills the order inside the raw ETF high/low range and
  all regenerated market-qualified records use `etf`.

- [ ] **Step 9: Add failing lock, earliest-date, independent-failure, and no-op tests**

  Add four tests:

  ```python
  def test_apply_locks_account_before_market_update(monkeypatch, ...):
      calls = []
      monkeypatch.setattr(PaperTradingRepository, "lock_account", record_lock)
      monkeypatch.setattr(PaperTradingRepository, "update_orders_market", record_update)
      HistoricalEtfMarketRepairService(...).run(apply=True)
      assert calls[:2] == ["lock", "update"]

  def test_apply_rebuilds_each_account_once_from_earliest_corrected_date(monkeypatch, ...):
      calls = []
      monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", record_rebuild)
      result = HistoricalEtfMarketRepairService(...).run(apply=True)
      assert calls == [(account.id, date(2026, 8, 7), [earlier.id, later.id])]
      assert result.repaired_accounts == [RepairedAccount(account.id, [earlier.id, later.id], date(2026, 8, 7))]

  def test_apply_rolls_back_failed_account_and_keeps_prior_account(monkeypatch, ...):
      monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", fail_second_account)
      result = HistoricalEtfMarketRepairService(...).run(apply=True)
      assert [item.account_id for item in result.repaired_accounts] == [first.id]
      assert [item.account_id for item in result.failed_accounts] == [second.id]
      assert first_order.market == Market.ETF.value
      assert second_order.market == Market.A_SHARE.value

  def test_second_apply_is_no_op_after_successful_repair(...):
      service.run(apply=True)
      second = service.run(apply=True)
      assert second.candidates == []
      assert second.corrected_orders == []
      assert second.repaired_accounts == []
      assert second.skipped_accounts == []
      assert second.failed_accounts == []
  ```

  In the failure test, seed separate file-backed sessions and ensure each
  account has a distinct candidate. `fail_second_account` must raise only when
  `account_id == second.id`; re-open a verification session after the service
  returns, so ORM identity-map state cannot conceal a rollback.

- [ ] **Step 10: Run service coverage**

  Run: `uv run pytest test/paper_trading/services/test_historical_etf_market_repair_service.py -v`

  Expected: PASS for dry-run, lock ordering, correction/replay, retained A-share
  diagnostic, no new ETF diagnostic, per-account failure isolation, earliest
  date, and no-op rerun.

- [ ] **Step 11: Format and inspect service changes**

  Run: `uv run ruff format paper_trading/services/historical_etf_market_repair_service.py test/paper_trading/services/test_historical_etf_market_repair_service.py`

  Expected: files formatted or already formatted.

  Run: `git diff --check -- paper_trading/services/historical_etf_market_repair_service.py test/paper_trading/services/test_historical_etf_market_repair_service.py`

  Expected: PASS with no whitespace errors. Leave changes unstaged.

### Task 3: Expose Repair Through Authenticated API

**Files:**
- Create: `paper_trading/schemas/repairs.py`
- Create: `paper_trading/api/routers/repairs.py`
- Modify: `paper_trading/api/deps.py:36-50`
- Modify: `paper_trading/api/app.py:6, 21-26`
- Test: `test/paper_trading/api/test_repairs_api.py`

**Interfaces:**
- Consumes: `HistoricalEtfMarketRepairService.run(apply: bool)`, `MarketDataProvider`, `Session`, and the existing API token dependency.
- Produces: `POST /paper/repairs/etf-markets`, `HistoricalEtfMarketRepairRequest`, `HistoricalEtfMarketRepairResponse`, and `get_session_factory() -> Callable[[], Session]`.

- [ ] **Step 1: Write failing API default-dry-run and authentication tests**

  Create `test/paper_trading/api/test_repairs_api.py`. Use a file-backed SQLite
  database and a `sessionmaker`; create all tables, create `ETFBasic`, seed a
  candidate, and commit. Override `get_session` with a new session per request,
  override the new `get_session_factory` with the same `sessionmaker`, and
  override market data with a raw ETF bar fake.

  Add tests:

  ```python
  def test_repair_api_requires_token(sqlite_factory):
      response = TestClient(create_app()).post("/paper/repairs/etf-markets")
      assert response.status_code == 401

  def test_repair_api_defaults_to_dry_run(monkeypatch, sqlite_factory):
      response = client.post("/paper/repairs/etf-markets", headers=AUTH_HEADERS)
      assert response.status_code == 200
      assert response.json()["dry_run"] is True
      assert response.json()["candidates"] == [{
          "account_id": account.id, "order_id": order.id, "symbol": "518880", "trade_date": "2026-08-07"
      }]
      assert reload_order(order.id).market == "a_share"
  ```

- [ ] **Step 2: Run the API tests and verify failure**

  Run: `uv run pytest test/paper_trading/api/test_repairs_api.py -v`

  Expected: FAIL because router, schemas, and session-factory dependency do not exist.

- [ ] **Step 3: Add request and response schemas**

  Create `paper_trading/schemas/repairs.py` using Pydantic models:

  ```python
  class HistoricalEtfMarketRepairRequest(BaseModel):
      apply: bool = False

  class RepairCandidateResponse(BaseModel):
      account_id: int
      order_id: int
      symbol: str
      trade_date: date

  class RepairedAccountResponse(BaseModel):
      account_id: int
      order_ids: list[int]
      replay_start_date: date

  class FailedAccountResponse(BaseModel):
      account_id: int
      error: str

  class HistoricalEtfMarketRepairResponse(BaseModel):
      dry_run: bool
      candidates: list[RepairCandidateResponse]
      corrected_orders: list[RepairCandidateResponse]
      repaired_accounts: list[RepairedAccountResponse]
      skipped_accounts: list[int]
      failed_accounts: list[FailedAccountResponse]
  ```

- [ ] **Step 4: Add a normal session-factory dependency**

  In `paper_trading/api/deps.py`, factor the `sessionmaker(bind=create_engine(url))`
  construction into `get_session_factory()`. Then implement `get_session()` by
  calling `get_session_factory()()`. Its annotation must be:

  ```python
  def get_session_factory() -> Callable[[], Session]:
  ```

  Import `Callable` from `collections.abc`. This keeps production repair
  sessions on the normal configured database and lets API tests override the
  factory with their file-backed SQLite `sessionmaker`.

- [ ] **Step 5: Implement and register the repair route**

  Create `paper_trading/api/routers/repairs.py`:

  ```python
  router = APIRouter(prefix="/paper/repairs", dependencies=[Depends(require_api_token)])

  @router.post("/etf-markets", response_model=HistoricalEtfMarketRepairResponse)
  def repair_historical_etf_markets(
      request: HistoricalEtfMarketRepairRequest,
      session_factory: Callable[[], Session] = Depends(get_session_factory),
      market_data: MarketDataProvider = Depends(get_market_data_provider),
  ) -> HistoricalEtfMarketRepairResponse:
      result = HistoricalEtfMarketRepairService(session_factory, market_data).run(request.apply)
      return HistoricalEtfMarketRepairResponse(
          dry_run=result.dry_run,
          candidates=[item.__dict__ for item in result.candidates],
          corrected_orders=[item.__dict__ for item in result.corrected_orders],
          repaired_accounts=[item.__dict__ for item in result.repaired_accounts],
          skipped_accounts=result.skipped_accounts,
          failed_accounts=[item.__dict__ for item in result.failed_accounts],
      )
  ```

  This explicit conversion avoids depending on recursive frozen-dataclass
  validation behavior. Preserve exactly the response field names above and
  register the router in `create_app`.

- [ ] **Step 6: Run default/authentication API coverage**

  Run: `uv run pytest test/paper_trading/api/test_repairs_api.py -k "requires_token or defaults_to_dry_run" -v`

  Expected: PASS. The omitted body field defaults to false and does not alter
  the persisted candidate.

- [ ] **Step 7: Add failing API apply outcome transport test**

  Post `{"apply": true}` with the raw ETF bar fake and assert exact response
  sections plus persisted state:

  ```python
  assert body["dry_run"] is False
  assert body["corrected_orders"] == [candidate_payload]
  assert body["repaired_accounts"] == [{
      "account_id": account.id, "order_ids": [order.id], "replay_start_date": "2026-08-07"
  }]
  assert body["skipped_accounts"] == []
  assert body["failed_accounts"] == []
  assert reload_order(order.id).market == "etf"
  ```

- [ ] **Step 8: Run full repair API coverage**

  Run: `uv run pytest test/paper_trading/api/test_repairs_api.py -v`

  Expected: PASS for auth, default dry-run, and explicit apply serialization.

- [ ] **Step 9: Check API scope**

  Run: `git diff --check -- paper_trading/api/deps.py paper_trading/api/app.py paper_trading/api/routers/repairs.py paper_trading/schemas/repairs.py test/paper_trading/api/test_repairs_api.py`

  Expected: PASS with no whitespace errors. Leave changes unstaged.

### Task 4: Add Paper Trading CLI Repair Command

**Files:**
- Modify: `tools/paper_trading_cli.py:11-39, 249-266, 401-416, 658-741`
- Test: `test/tools/test_paper_trading_cli.py:1558-1695`

**Interfaces:**
- Consumes: `POST /paper/repairs/etf-markets` and `PaperTradingApiClient._request`.
- Produces: `PaperTradingApiClient.repair_historical_etf_markets(apply: bool = False) -> dict[str, Any]` and `repair etf-markets [--apply]`.

- [ ] **Step 1: Add failing CLI tests**

  Add a `TestRepairHistoricalEtfMarkets` class near matching CLI tests. Set
  `client.repair_historical_etf_markets.return_value` to a structured dry-run
  response. Test the default and apply cases:

  ```python
  def test_repair_etf_markets_defaults_to_dry_run():
      code = main(["repair", "etf-markets"], client=client)
      assert code == EXIT_CODES["OK"]
      client.repair_historical_etf_markets.assert_called_once_with(apply=False)

  def test_repair_etf_markets_forwards_apply_flag():
      code = main(["repair", "etf-markets", "--apply"], client=client)
      assert code == EXIT_CODES["OK"]
      client.repair_historical_etf_markets.assert_called_once_with(apply=True)

  def test_repair_etf_markets_json_output(capsys):
      code = main(["--json", "repair", "etf-markets"], client=client)
      assert code == EXIT_CODES["OK"]
      assert json.loads(capsys.readouterr().out)["dry_run"] is True
  ```

  Add a direct client transport test using a mocked `_request`:

  ```python
  client._request = Mock(return_value={"dry_run": False})
  assert client.repair_historical_etf_markets(apply=True) == {"dry_run": False}
  client._request.assert_called_once_with("POST", "/paper/repairs/etf-markets", json={"apply": True})
  ```

- [ ] **Step 2: Run CLI tests and verify failure**

  Run: `uv run pytest test/tools/test_paper_trading_cli.py -k "repair_etf_markets or historical_etf_markets" -v`

  Expected: FAIL because the parser and client method do not exist.

- [ ] **Step 3: Add the client request method and usage entry**

  Add this method after `rebuild_delayed_daily_bar_orders`:

  ```python
  def repair_historical_etf_markets(self, apply: bool = False) -> dict[str, Any]:
      return self._request("POST", "/paper/repairs/etf-markets", json={"apply": apply})
  ```

  Add `repair etf-markets [--apply]` to the module usage text.

- [ ] **Step 4: Add parser and command handler**

  Define `_add_repair_subparsers`:

  ```python
  def _add_repair_subparsers(subparsers: Any) -> None:
      repair = subparsers.add_parser("repair", help="Run explicit paper trading repairs")
      repair_sub = repair.add_subparsers(dest="repair_command", required=True, parser_class=_SafeParser)
      etf_markets = repair_sub.add_parser(
          "etf-markets", help="Preview or repair historical catalogue ETF market identity"
      )
      etf_markets.add_argument("--apply", action="store_true", help="Apply the repair; default is dry run")
  ```

  Register it in `build_parser`. Define `_handle_repair` that accepts only
  `etf-markets` and returns
  `client.repair_historical_etf_markets(apply=args.apply)`. Add `repair` to
  `_HANDLERS` and `repair_command` to `_get_subcommand`.

- [ ] **Step 5: Run CLI coverage**

  Run: `uv run pytest test/tools/test_paper_trading_cli.py -k "repair_etf_markets or historical_etf_markets" -v`

  Expected: PASS. The omitted flag sends an explicit false body, `--apply`
  sends true, and JSON output preserves the API response.

- [ ] **Step 6: Run parser regression coverage**

  Run: `uv run pytest test/tools/test_paper_trading_cli.py -k "matching or repair_etf_markets or historical_etf_markets" -v`

  Expected: PASS. Existing matching subcommands and error paths remain intact.

- [ ] **Step 7: Format and inspect CLI changes**

  Run: `uv run ruff format tools/paper_trading_cli.py test/tools/test_paper_trading_cli.py`

  Expected: files formatted or already formatted.

  Run: `git diff --check -- tools/paper_trading_cli.py test/tools/test_paper_trading_cli.py`

  Expected: PASS with no whitespace errors. Leave changes unstaged.

### Task 5: Verify Completed Repair Surface

**Files:**
- Modify only if verification identifies a defect: files listed in Tasks 1-4.
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/services/test_historical_etf_market_repair_service.py`
- Test: `test/paper_trading/api/test_repairs_api.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: completed repair repository, service, API, and CLI surfaces.
- Produces: focused behavioral, formatting, lint, type, and PostgreSQL integration evidence for issue #56.

- [ ] **Step 1: Run all new focused tests**

  Run: `uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_historical_etf_market_repair_service.py test/paper_trading/api/test_repairs_api.py test/tools/test_paper_trading_cli.py -v`

  Expected: PASS. This proves discovery, dry-run non-mutation, per-account
  application and rollback, raw ETF replay, API auth/transport, and CLI flags.

- [ ] **Step 2: Run dependent Paper Trading regressions**

  Run: `uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py -v`

  Expected: PASS. Existing account replay, raw ETF matching, diagnostics, and
  delayed-bar rebuild semantics are unchanged.

- [ ] **Step 3: Run lint and type checks for the changed surface**

  Run: `uv run ruff check paper_trading/storage/repository.py paper_trading/services/historical_etf_market_repair_service.py paper_trading/api/deps.py paper_trading/api/app.py paper_trading/api/routers/repairs.py paper_trading/schemas/repairs.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_historical_etf_market_repair_service.py test/paper_trading/api/test_repairs_api.py test/tools/test_paper_trading_cli.py`

  Expected: PASS.

  Run: `uv run mypy`

  Expected: PASS.

- [ ] **Step 4: Run PostgreSQL-integrated coverage**

  Run: `tools/run_tests.sh test/paper_trading/storage/test_repository.py test/paper_trading/services/test_historical_etf_market_repair_service.py test/paper_trading/api/test_repairs_api.py -v`

  Expected: PASS. The isolated PostgreSQL runner verifies the catalogue join,
  enum-backed ETF updates, locks, and account-level transactions in the
  repository's integration environment.

- [ ] **Step 5: Inspect final scope and whitespace**

  Run: `git diff --check`

  Expected: PASS with no whitespace errors.

  Run: `git diff -- paper_trading/storage/repository.py paper_trading/services/historical_etf_market_repair_service.py paper_trading/api/deps.py paper_trading/api/app.py paper_trading/api/routers/repairs.py paper_trading/schemas/repairs.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_historical_etf_market_repair_service.py test/paper_trading/api/test_repairs_api.py test/tools/test_paper_trading_cli.py`

  Expected: only issue #56 repair discovery, independent account repair,
  authenticated transport, CLI operation, and their tests. There must be no
  changes to normal matching behavior, ETF eligibility policy, schema
  migrations, or historical diagnostic deletion.

- [ ] **Step 6: Report evidence and leave changes unstaged**

  Report every command's exit status, test count when available, and blockers.
  Do not stage or commit unless the user explicitly requests it.

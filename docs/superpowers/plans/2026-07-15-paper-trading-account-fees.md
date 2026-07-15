# Paper Trading Account Fee Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional account-level paper trading fee configuration at account creation time, using the built-in `a_share` preset when fields are omitted.

**Architecture:** Define built-in fee presets in the fee domain module, store the selected preset and effective fee parameters directly on `paper_accounts`, expose them through account schemas, and pass account-derived `FeeConfig` into existing fee calculation. Keep the current default behavior for callers that omit fee fields by using `a_share`.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Decimal, pytest, uv.

## Global Constraints

- Use `uv run` for Python commands in this repo.
- Built-in preset `a_share` must remain `commission_rate=0.0003`, `min_commission=5.00`, `stamp_duty_rate=0.0005`, `transfer_fee_rate=0.00001`.
- Account creation defaults to `fee_preset=a_share` when `fee_preset` is omitted.
- Fee values must be non-negative decimals; zero is valid.
- No API or CLI support for updating fees after account creation.
- No per-order fee overrides, reusable fee profiles, or historical fee recalculation.
- Keep old account creation payloads and CLI invocations working unchanged.

---

## File Structure

- Modify `storage/model/paper_trading.py`: add `fee_preset` and fee columns to `PaperAccount`.
- Modify `storage/storage_db.py`: add startup upgrade columns for existing `paper_accounts` tables.
- Modify `paper_trading/domain/fees.py`: add preset constants, preset resolution, and a helper that builds `FeeConfig` from account-like objects.
- Modify `paper_trading/storage/repository.py`: accept and persist optional preset and fee values during account creation.
- Modify `paper_trading/services/account_service.py`: pass optional fee values through.
- Modify `paper_trading/schemas/accounts.py`: request/response fee fields and non-negative validation.
- Modify `paper_trading/api/routers/accounts.py`: pass optional fee values into account service.
- Modify `paper_trading/services/order_service.py`: use account fee config when freezing buy cash.
- Modify `paper_trading/services/matching_service.py`: use account fee config when calculating trade fees.
- Modify `tools/paper_trading_cli.py`: add optional create-account fee flags and request fields.
- Modify tests under `test/paper_trading/` and `test/tools/test_paper_trading_cli.py`.
- Modify `docs/paper_trading.md`: document API and CLI fee fields.

---

### Task 1: Persist Account Fee Configuration

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `storage/storage_db.py`
- Modify: `paper_trading/domain/fees.py`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/account_service.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Produces: `DEFAULT_FEE_PRESET = "a_share"`
- Produces: `get_fee_preset(name: str | None = None) -> FeeConfig`
- Produces: `fee_config_from_account(account: Any) -> FeeConfig`
- Produces: `PaperTradingRepository.create_account(name: str, initial_cash: Decimal, fee_preset: str | None = None, commission_rate: Decimal | None = None, min_commission: Decimal | None = None, stamp_duty_rate: Decimal | None = None, transfer_fee_rate: Decimal | None = None) -> PaperAccount`
- Produces: `AccountService.create_account(...) -> PaperAccount` with the same optional fee parameters.

- [ ] **Step 1: Write failing repository tests**

Add these tests to `test/paper_trading/storage/test_repository.py`:

```python
def test_create_account_sets_default_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00030000")
    assert account.min_commission == Decimal("5.0000")
    assert account.stamp_duty_rate == Decimal("0.00050000")
    assert account.transfer_fee_rate == Decimal("0.00001000")
    engine.dispose()


def test_create_account_accepts_custom_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(
        name="custom-fee",
        initial_cash=Decimal("100000.00"),
        fee_preset="a_share",
        commission_rate=Decimal("0.00025"),
        min_commission=Decimal("3.00"),
        stamp_duty_rate=Decimal("0.0004"),
        transfer_fee_rate=Decimal("0.00002"),
    )
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00025000")
    assert account.min_commission == Decimal("3.0000")
    assert account.stamp_duty_rate == Decimal("0.00040000")
    assert account.transfer_fee_rate == Decimal("0.00002000")
    engine.dispose()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py::test_create_account_sets_default_fee_config test/paper_trading/storage/test_repository.py::test_create_account_accepts_custom_fee_config -q`

Expected: FAIL because `PaperAccount` has no fee attributes or `create_account` has no optional fee parameters.

- [ ] **Step 3: Implement persistence and helper**

In `storage/model/paper_trading.py`, add these columns to `PaperAccount` after `initial_cash`:

```python
    fee_preset = Column(String(30), nullable=False, server_default="a_share")
    commission_rate = Column(Numeric(20, 8), nullable=False, server_default=text("0.0003"))
    min_commission = Column(Numeric(20, 4), nullable=False, server_default=text("5.00"))
    stamp_duty_rate = Column(Numeric(20, 8), nullable=False, server_default=text("0.0005"))
    transfer_fee_rate = Column(Numeric(20, 8), nullable=False, server_default=text("0.00001"))
```

In `paper_trading/domain/fees.py`, add:

```python
from typing import Any

DEFAULT_FEE_PRESET = "a_share"
FEE_PRESETS: dict[str, FeeConfig] = {
    DEFAULT_FEE_PRESET: FeeConfig(),
}


def get_fee_preset(name: str | None = None) -> FeeConfig:
    preset_name = name or DEFAULT_FEE_PRESET
    try:
        return FEE_PRESETS[preset_name]
    except KeyError as exc:
        raise ValueError(f"unknown fee preset: {preset_name}") from exc


def fee_config_from_account(account: Any) -> FeeConfig:
    default = get_fee_preset(getattr(account, "fee_preset", None))
    return FeeConfig(
        commission_rate=Decimal(account.commission_rate)
        if account.commission_rate is not None
        else default.commission_rate,
        min_commission=Decimal(account.min_commission) if account.min_commission is not None else default.min_commission,
        stamp_duty_rate=Decimal(account.stamp_duty_rate)
        if account.stamp_duty_rate is not None
        else default.stamp_duty_rate,
        transfer_fee_rate=Decimal(account.transfer_fee_rate)
        if account.transfer_fee_rate is not None
        else default.transfer_fee_rate,
    )
```

In `paper_trading/storage/repository.py`, change `create_account` to:

```python
    def create_account(
        self,
        name: str,
        initial_cash: Decimal,
        fee_preset: str | None = None,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount:
        preset_name = fee_preset or DEFAULT_FEE_PRESET
        preset = get_fee_preset(preset_name)
        account = PaperAccount(
            name=name,
            initial_cash=initial_cash,
            fee_preset=preset_name,
            commission_rate=commission_rate if commission_rate is not None else preset.commission_rate,
            min_commission=min_commission if min_commission is not None else preset.min_commission,
            stamp_duty_rate=stamp_duty_rate if stamp_duty_rate is not None else preset.stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate if transfer_fee_rate is not None else preset.transfer_fee_rate,
        )
        self.session.add(account)
        self.session.flush()
        self.add_cash_event(account.id, CashEventType.DEPOSIT, initial_cash, note="initial_cash")
        return account
```

In `paper_trading/services/account_service.py`, change `create_account` to pass through the optional fields.

In `storage/storage_db.py`, update `ensure_paper_trading_schema` to import `tb_name_paper_accounts`, inspect `paper_accounts`, and add missing fee columns for existing databases:

```python
        if inspect(self.engine).has_table(tb_name_paper_accounts):
            account_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_accounts)}
            account_fee_columns = {
                "fee_preset": "VARCHAR(30) NOT NULL DEFAULT 'a_share'",
                "commission_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.0003",
                "min_commission": "NUMERIC(20, 4) NOT NULL DEFAULT 5.00",
                "stamp_duty_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.0005",
                "transfer_fee_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.00001",
            }
            for column_name, ddl in account_fee_columns.items():
                if column_name not in account_columns:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN {column_name} {ddl}"))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest test/paper_trading/storage/test_repository.py::test_create_account_sets_default_fee_config test/paper_trading/storage/test_repository.py::test_create_account_accepts_custom_fee_config -q`

Expected: PASS.

---

### Task 2: Expose Fee Configuration Through API and CLI

**Files:**
- Modify: `paper_trading/schemas/accounts.py`
- Modify: `paper_trading/api/routers/accounts.py`
- Modify: `tools/paper_trading_cli.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: `AccountService.create_account` optional fee parameters from Task 1.
- Produces: `CreateAccountRequest` optional `fee_preset` and fee fields with validation.
- Produces: `PaperTradingApiClient.create_account(...)` optional fee parameters.

- [ ] **Step 1: Write failing API test**

Add to `test/paper_trading/api/test_accounts_api.py`:

```python
def test_create_account_accepts_and_returns_fee_config(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={
            "name": "custom-fee",
            "initial_cash": "100000.00",
            "fee_preset": "a_share",
            "commission_rate": "0.00025",
            "min_commission": "3.00",
            "stamp_duty_rate": "0.0004",
            "transfer_fee_rate": "0.00002",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fee_preset"] == "a_share"
    assert body["commission_rate"] == "0.00025000"
    assert body["min_commission"] == "3.0000"
    assert body["stamp_duty_rate"] == "0.00040000"
    assert body["transfer_fee_rate"] == "0.00002000"


def test_create_account_rejects_negative_fee_config(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "bad-fee", "initial_cash": "100000.00", "commission_rate": "-0.0001"},
        headers=headers,
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Write failing CLI test**

Add to `TestAccountCreate` in `test/tools/test_paper_trading_cli.py`:

```python
    def test_create_account_passes_fee_config(self):
        client = _mock_client()
        with patch("tools.paper_trading_cli.PaperTradingApiClient", return_value=client):
            rc = main(
                [
                    "--base-url",
                    "http://localhost:8000",
                    "--token",
                    "token",
                    "account",
                    "create",
                    "--name",
                    "custom-fee",
                    "--initial-cash",
                    "100000.00",
                    "--fee-preset",
                    "a_share",
                    "--commission-rate",
                    "0.00025",
                    "--min-commission",
                    "3.00",
                    "--stamp-duty-rate",
                    "0.0004",
                    "--transfer-fee-rate",
                    "0.00002",
                ]
            )

        assert rc == EXIT_CODES["success"]
        client.create_account.assert_called_once_with(
            name="custom-fee",
            initial_cash=Decimal("100000.00"),
            fee_preset="a_share",
            commission_rate=Decimal("0.00025"),
            min_commission=Decimal("3.00"),
            stamp_duty_rate=Decimal("0.0004"),
            transfer_fee_rate=Decimal("0.00002"),
        )
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py::test_create_account_accepts_and_returns_fee_config test/paper_trading/api/test_accounts_api.py::test_create_account_rejects_negative_fee_config test/tools/test_paper_trading_cli.py::TestAccountCreate::test_create_account_passes_fee_config -q`

Expected: FAIL because schemas and CLI do not expose fee fields yet.

- [ ] **Step 4: Implement API and CLI support**

In `paper_trading/schemas/accounts.py`, add `Field` and fee fields:

```python
from pydantic import BaseModel, ConfigDict, Field


class CreateAccountRequest(BaseModel):
    name: str
    initial_cash: Decimal
    fee_preset: str | None = "a_share"
    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    initial_cash: Decimal
    fee_preset: str
    commission_rate: Decimal
    min_commission: Decimal
    stamp_duty_rate: Decimal
    transfer_fee_rate: Decimal
    status: str
    base_currency: str
```

In `paper_trading/api/routers/accounts.py`, pass the request fields into `create_account`. Reject unknown presets with HTTP 422.

In `tools/paper_trading_cli.py`, extend `PaperTradingApiClient.create_account` to accept optional `fee_preset` and fee parameters, include only non-`None` values in the JSON body, add `--fee-preset` and the four parser flags, and pass parsed decimals from `_handle_account`.

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py test/tools/test_paper_trading_cli.py::TestAccountCreate -q`

Expected: PASS.

---

### Task 3: Use Account Fee Configuration for Orders and Matching

**Files:**
- Modify: `paper_trading/services/order_service.py`
- Modify: `paper_trading/services/matching_service.py`
- Test: `test/paper_trading/services/test_order_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: `fee_config_from_account(account: Any) -> FeeConfig` from Task 1.
- Produces: buy order cash freeze and trade fees based on account configuration.

- [ ] **Step 1: Write failing order-service test**

Add to `test/paper_trading/services/test_order_service.py`:

```python
def test_place_buy_order_uses_account_fee_config(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account(
        "custom-fee",
        Decimal("100000.00"),
        commission_rate=Decimal("0.001"),
        min_commission=Decimal("1.00"),
        stamp_duty_rate=Decimal("0.0005"),
        transfer_fee_rate=Decimal("0"),
    )

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.frozen_cash == Decimal("1001.0000")
    assert repo.get_cash_available(account.id) == Decimal("98999.0000")
    engine.dispose()
```

- [ ] **Step 2: Write failing matching-service test**

Add to `test/paper_trading/services/test_matching_service.py`:

```python
def test_matching_uses_account_fee_config_for_trade_fees(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account(
        "custom-fee",
        Decimal("100000.00"),
        commission_rate=Decimal("0.001"),
        min_commission=Decimal("1.00"),
        stamp_duty_rate=Decimal("0.0005"),
        transfer_fee_rate=Decimal("0"),
    )
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    matching_service.run(trade_date)
    session.commit()

    trades = repo.list_trades(account.id)
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert trades[0].fees == Decimal("1.0000")
    assert repo.get_cash_available(account.id) == Decimal("98999.0000")
    engine.dispose()
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_place_buy_order_uses_account_fee_config test/paper_trading/services/test_matching_service.py::test_matching_uses_account_fee_config_for_trade_fees -q`

Expected: FAIL because services still use default fee configuration.

- [ ] **Step 4: Implement service fee lookup**

In `paper_trading/services/order_service.py`, import `fee_config_from_account` and change buy freeze calculation:

```python
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"paper account not found: {account_id}")
        amount = Decimal(quantity) * limit_price
        fee_config = fee_config_from_account(account)
        frozen_cash = (amount + calculate_a_share_fees(OrderSide.BUY, amount, fee_config).total).quantize(
            Decimal("0.0001")
        )
```

In `paper_trading/services/matching_service.py`, import `fee_config_from_account` and change `_fill_order`:

```python
        account = self.repo.get_account(order.account_id)
        if account is None:
            raise ValueError(f"paper account not found: {order.account_id}")
        amount = (Decimal(quantity) * price).quantize(Decimal("0.0001"))
        fees = calculate_a_share_fees(side, amount, fee_config_from_account(account)).total.quantize(Decimal("0.0001"))
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_place_buy_order_uses_account_fee_config test/paper_trading/services/test_matching_service.py::test_matching_uses_account_fee_config_for_trade_fees -q`

Expected: PASS.

---

### Task 4: Documentation and Full Verification

**Files:**
- Modify: `docs/paper_trading.md`
- Test: relevant paper trading and CLI tests.

**Interfaces:**
- Consumes: completed API and CLI behavior from Tasks 1-3.
- Produces: user-facing documentation for account fee configuration.

- [ ] **Step 1: Update docs**

In `docs/paper_trading.md`, update the account creation section or CLI section to include:

```bash
uv run tools/paper_trading_cli.py account create \
  --name demo \
  --initial-cash 100000 \
  --fee-preset a_share \
  --commission-rate 0.00025 \
  --min-commission 5.00 \
  --stamp-duty-rate 0.0005 \
  --transfer-fee-rate 0.00001
```

Document that all fee flags are optional, omitted values use `--fee-preset a_share`, and `a_share` matches the previous hardcoded A-share fees.

- [ ] **Step 2: Run focused verification**

Run: `uv run pytest test/paper_trading/domain/test_fees.py test/paper_trading/storage/test_repository.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/tools/test_paper_trading_cli.py -q`

Expected: PASS.

- [ ] **Step 3: Run formatting and lint on touched files**

Run: `uv run ruff format storage/model/paper_trading.py storage/storage_db.py paper_trading/domain/fees.py paper_trading/storage/repository.py paper_trading/services/account_service.py paper_trading/schemas/accounts.py paper_trading/api/routers/accounts.py paper_trading/services/order_service.py paper_trading/services/matching_service.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/tools/test_paper_trading_cli.py`

Expected: files formatted or left unchanged.

Run: `uv run ruff check storage/model/paper_trading.py storage/storage_db.py paper_trading/domain/fees.py paper_trading/storage/repository.py paper_trading/services/account_service.py paper_trading/schemas/accounts.py paper_trading/api/routers/accounts.py paper_trading/services/order_service.py paper_trading/services/matching_service.py tools/paper_trading_cli.py test/paper_trading/storage/test_repository.py test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/tools/test_paper_trading_cli.py`

Expected: PASS.

- [ ] **Step 4: Final status check**

Run: `git status --short`

Expected: only intended plan/spec/code/test/doc files are modified.

---

## Self-Review

- Spec coverage: preset definitions, data model, API, CLI, service flow, validation, tests, docs, and non-goals are covered by Tasks 1-4.
- Placeholder scan: no `TBD`, `TODO`, or unresolved implementation placeholders remain.
- Type consistency: optional fee parameters use `Decimal | None` through schema/service/repository/CLI and are converted to existing `FeeConfig` for calculations.

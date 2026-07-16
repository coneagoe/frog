# Paper Trading Account Fee Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow an existing paper trading account to update fee fields after creation, with the new values applying only to future orders and trades.

**Architecture:** Keep fee values on the existing `paper_accounts` row as the source of truth. Add a PATCH account-fee update path through schema → service → repository → API → CLI, and make sure order freezing and matching continue to read the account row at execution time so updates affect only future work.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Typer/argparse CLI wrapper, Pytest, Ruff.

## Global Constraints

- Support partial updates: callers may provide one or more fee fields.
- Do not require or accept `fee_preset` in the update flow.
- Do not recalculate historical data.
- New orders and future trade settlement must use the updated fee values.
- Historical orders, trades, and cash movements must remain unchanged.
- Reject negative fee values.
- Reject empty update requests.
- Unknown account IDs must keep the existing 404 response shape.

---

### Task 1: Add update schema and repository/service support

**Files:**
- Modify: `paper_trading/schemas/accounts.py`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/account_service.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/services/test_account_service.py`

**Interfaces:**
- Consumes: `PaperTradingRepository.get_account`, `PaperTradingRepository.create_account`
- Produces: `PaperTradingRepository.update_account_fees(account_id: int, commission_rate: Decimal | None = None, min_commission: Decimal | None = None, stamp_duty_rate: Decimal | None = None, transfer_fee_rate: Decimal | None = None) -> PaperAccount | None`
- Produces: `AccountService.update_account_fees(...) -> PaperAccount | None`
- Produces: `UpdateAccountFeeRequest` or similar Pydantic model with only the four optional fee fields

- [ ] **Step 1: Write the failing repository tests**

```python
def test_update_account_fees_updates_only_provided_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    updated = repo.update_account_fees(
        account.id,
        commission_rate=Decimal("0.0002"),
        min_commission=Decimal("3.00"),
    )
    session.commit()

    assert updated is not None
    assert updated.commission_rate == Decimal("0.00020000")
    assert updated.min_commission == Decimal("3.0000")
    assert updated.stamp_duty_rate == Decimal("0.00050000")
    assert updated.transfer_fee_rate == Decimal("0.00001000")
```

```python
def test_update_account_fees_rejects_negative_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    with pytest.raises(ValueError, match="commission_rate"):
        repo.update_account_fees(account.id, commission_rate=Decimal("-0.0001"))
```

```python
def test_update_account_fees_returns_none_for_missing_account(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    assert repo.update_account_fees(999, commission_rate=Decimal("0.0002")) is None
```

- [ ] **Step 2: Run the repository tests and confirm they fail first**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -q`
Expected: fail because `update_account_fees` does not exist yet.

- [ ] **Step 3: Add the minimal repository implementation**

```python
def update_account_fees(
    self,
    account_id: int,
    commission_rate: Decimal | None = None,
    min_commission: Decimal | None = None,
    stamp_duty_rate: Decimal | None = None,
    transfer_fee_rate: Decimal | None = None,
) -> PaperAccount | None:
    _validate_fee_values(
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_duty_rate=stamp_duty_rate,
        transfer_fee_rate=transfer_fee_rate,
    )
    account = self.get_account(account_id)
    if account is None:
        return None
    if commission_rate is not None:
        account.commission_rate = commission_rate
    if min_commission is not None:
        account.min_commission = min_commission
    if stamp_duty_rate is not None:
        account.stamp_duty_rate = stamp_duty_rate
    if transfer_fee_rate is not None:
        account.transfer_fee_rate = transfer_fee_rate
    self.session.flush()
    return account
```

```python
class AccountService:
    def update_account_fees(
        self,
        account_id: int,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        return self.repo.update_account_fees(
            account_id=account_id,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
```

```python
class UpdateAccountFeeRequest(BaseModel):
    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)
```

- [ ] **Step 4: Run the repository and service tests until they pass**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_account_service.py -q`
Expected: PASS.

### Task 2: Add the PATCH account fee API

**Files:**
- Modify: `paper_trading/api/routers/accounts.py`
- Modify: `paper_trading/schemas/accounts.py`
- Test: `test/paper_trading/api/test_accounts_api.py`

**Interfaces:**
- Consumes: `AccountService.update_account_fees`, `UpdateAccountFeeRequest`
- Produces: `PATCH /paper/accounts/{account_id}` returning `AccountResponse`

- [ ] **Step 1: Write the failing API tests**

```python
def test_update_account_fees_updates_existing_account(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(
        f"/paper/accounts/{created['id']}",
        json={"commission_rate": "0.0002", "min_commission": "3.00"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["commission_rate"] == "0.00020000"
    assert body["min_commission"] == "3.0000"
```

```python
def test_update_account_fees_rejects_empty_payload(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(f"/paper/accounts/{created['id']}", json={}, headers=headers)

    assert response.status_code == 422
```

```python
def test_update_account_fees_returns_404_for_missing_account(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.patch(
        "/paper/accounts/999",
        json={"commission_rate": "0.0002"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"
```

- [ ] **Step 2: Run the API tests and confirm they fail first**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py -q`
Expected: fail because the PATCH route does not exist yet.

- [ ] **Step 3: Add the route and request validation**

```python
@router.patch("/{account_id}", response_model=AccountResponse)
def update_account_fees(
    account_id: int,
    request: UpdateAccountFeeRequest,
    session: Session = Depends(get_session),
):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="at least one fee field is required")
    repo = PaperTradingRepository(session)
    service = AccountService(repo)
    try:
        account = service.update_account_fees(account_id=account_id, **payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    session.commit()
    return account
```

- [ ] **Step 4: Run the API tests until they pass**

Run: `uv run pytest test/paper_trading/api/test_accounts_api.py -q`
Expected: PASS.

### Task 3: Add the CLI fee update command

**Files:**
- Modify: `tools/paper_trading_cli.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: `PaperTradingApiClient._request`
- Produces: `PaperTradingApiClient.update_account_fees(...) -> dict[str, Any]`
- Produces: `account update-fee` CLI subcommand

- [ ] **Step 1: Write the failing CLI tests**

```python
def test_update_account_fees_calls_client_with_partial_payload(self):
    client = _mock_client()
    client.update_account_fees.return_value = client.get_account.return_value

    exit_code = main(
        [
            "account",
            "update-fee",
            "--account-id",
            "1",
            "--commission-rate",
            "0.0002",
            "--min-commission",
            "3",
        ],
        client=client,
    )

    assert exit_code == EXIT_CODES["OK"]
    client.update_account_fees.assert_called_once()
```

```python
def test_update_account_fees_rejects_empty_payload(self):
    client = _mock_client()

    exit_code = main(["account", "update-fee", "--account-id", "1"], client=client)

    assert exit_code == EXIT_CODES["VALIDATION_ERROR"]
```

- [ ] **Step 2: Run the CLI tests and confirm they fail first**

Run: `uv run pytest test/tools/test_paper_trading_cli.py -q`
Expected: fail because `update-fee` is not wired yet.

- [ ] **Step 3: Add the CLI wiring**

```python
def update_account_fees(
    self,
    account_id: int,
    commission_rate: Decimal | None = None,
    min_commission: Decimal | None = None,
    stamp_duty_rate: Decimal | None = None,
    transfer_fee_rate: Decimal | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if commission_rate is not None:
        body["commission_rate"] = str(commission_rate)
    if min_commission is not None:
        body["min_commission"] = str(min_commission)
    if stamp_duty_rate is not None:
        body["stamp_duty_rate"] = str(stamp_duty_rate)
    if transfer_fee_rate is not None:
        body["transfer_fee_rate"] = str(transfer_fee_rate)
    return self._request("PATCH", f"/paper/accounts/{account_id}", json=body)
```

```python
p_update = acct_sub.add_parser("update-fee", help="Update account fee fields")
p_update.add_argument("--account-id", type=int, required=True, help="Account ID")
p_update.add_argument("--commission-rate", default=None, help="Commission rate override")
p_update.add_argument("--min-commission", default=None, help="Minimum commission override")
p_update.add_argument("--stamp-duty-rate", default=None, help="Stamp duty rate override")
p_update.add_argument("--transfer-fee-rate", default=None, help="Transfer fee rate override")
```

```python
if cmd == "update-fee":
    kwargs: dict[str, Any] = {}
    if args.commission_rate is not None:
        kwargs["commission_rate"] = _parse_decimal(args.commission_rate, "--commission-rate")
    if args.min_commission is not None:
        kwargs["min_commission"] = _parse_decimal(args.min_commission, "--min-commission")
    if args.stamp_duty_rate is not None:
        kwargs["stamp_duty_rate"] = _parse_decimal(args.stamp_duty_rate, "--stamp-duty-rate")
    if args.transfer_fee_rate is not None:
        kwargs["transfer_fee_rate"] = _parse_decimal(args.transfer_fee_rate, "--transfer-fee-rate")
    if not kwargs:
        raise _ParserError("at least one fee field is required")
    return client.update_account_fees(account_id=args.account_id, **kwargs)
```

- [ ] **Step 4: Run the CLI tests until they pass**

Run: `uv run pytest test/tools/test_paper_trading_cli.py -q`
Expected: PASS.

### Task 4: Document the new fee update flow

**Files:**
- Modify: `docs/paper_trading.md`
- Test: none

**Interfaces:**
- Consumes: final API and CLI behavior from prior tasks
- Produces: updated backend documentation for post-creation fee edits

- [ ] **Step 1: Update the docs with the new command and API behavior**

Add a short section after account creation that shows:

```bash
uv run tools/paper_trading_cli.py account update-fee --account-id 1 --commission-rate 0.0002 --min-commission 3
```

Explain that:

- fee changes apply only to future orders and trades;
- historical trades and cash ledger entries are not recalculated;
- `fee_preset` is not changed by the update command.

- [ ] **Step 2: Keep the existing creation-time fee documentation intact**

Do not remove the current account creation fee docs; extend them with the new update flow.

## Verification

Run the focused tests in this order after implementation:

1. `uv run pytest test/paper_trading/storage/test_repository.py -q`
2. `uv run pytest test/paper_trading/services/test_account_service.py -q`
3. `uv run pytest test/paper_trading/api/test_accounts_api.py -q`
4. `uv run pytest test/tools/test_paper_trading_cli.py -q`
5. `uv run pytest test -q`

Then run repo checks if the change touches shared code:

- `uv run ruff check .`
- `uv run pytest test`

## Spec Coverage Check

- Update existing account fees after creation: Task 1, Task 2, Task 3.
- Partial updates only: Task 1, Task 2, Task 3.
- No fee preset switching: Task 1 schema, Task 2 validation, Task 4 docs.
- No historical recalculation: Goal, Scope, Verification, Task 4 docs.
- New transactions use new fees: Task 1 service/repository behavior, Task 2 API, Task 4 docs.
- Empty request rejected: Task 2 API, Task 3 CLI validation.
- Negative values rejected: Task 1 repository validation, Task 2 API.
- Existing 404 behavior preserved: Task 2 API.

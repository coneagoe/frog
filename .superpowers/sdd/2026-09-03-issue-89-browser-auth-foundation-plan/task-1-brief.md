### Task 1: Add Dependencies and Configuration Contracts

**Depends on:** None.

**Files:**
- Modify: `pyproject.toml:10-38`
- Modify: `uv.lock`
- Create: `paper_trading/auth/__init__.py`
- Test: `test/paper_trading/auth/test_auth_service.py`

**Interfaces:**
- Produces `AuthSettings.from_environment() -> AuthSettings` with `jwt_secret: str`, `jwt_ttl_seconds: int`, `cookie_secure: bool`, `session_cookie_name: str`, and `csrf_cookie_name: str`.
- Produces `validate_auth_settings(settings: AuthSettings, environment: str | None = None) -> None`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_production_settings_require_jwt_secret(monkeypatch):
    monkeypatch.delenv("PAPER_TRADING_JWT_SECRET", raising=False)
    monkeypatch.setenv("FROG_ENV", "production")
    with pytest.raises(ValueError, match="JWT secret"):
        AuthSettings.from_environment()


def test_production_settings_reject_insecure_cookie(monkeypatch):
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-secret")
    monkeypatch.setenv("FROG_ENV", "production")
    monkeypatch.setenv("PAPER_TRADING_COOKIE_SECURE", "false")
    with pytest.raises(ValueError, match="secure"):
        AuthSettings.from_environment()
```

- [ ] **Step 2: Run the focused test and verify the failure**

Run: `uv run pytest test/paper_trading/auth/test_auth_service.py::test_production_settings_require_jwt_secret test/paper_trading/auth/test_auth_service.py::test_production_settings_reject_insecure_cookie -v`

Expected: FAIL because the auth settings type and loader do not exist.

- [ ] **Step 3: Add the explicit runtime dependencies**

Add `argon2-cffi` and `PyJWT` to `project.dependencies` in `pyproject.toml`, preserving the project’s bounded-version style, then run `uv lock` to update only `uv.lock` and the corresponding package metadata.

- [ ] **Step 4: Implement the minimal settings loader**

Implement `AuthSettings.from_environment()` with local-test-safe defaults, production validation, explicit boolean parsing, positive integer TTL validation, and stable cookie-name defaults. Keep secret values out of exception text and logs.

- [ ] **Step 5: Run the configuration tests**

Run: `uv run pytest test/paper_trading/auth/test_auth_service.py::test_production_settings_require_jwt_secret test/paper_trading/auth/test_auth_service.py::test_production_settings_reject_insecure_cookie -v`

Expected: PASS.

- [ ] **Step 6: Commit the dependency/config slice**

```bash
git add pyproject.toml uv.lock paper_trading/auth/__init__.py test/paper_trading/auth/test_auth_service.py
git commit -m "feat: add browser auth dependencies and settings"
```

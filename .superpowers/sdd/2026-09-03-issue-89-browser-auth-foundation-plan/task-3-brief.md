### Task 3: Implement Pure Authentication Primitives

**Depends on:** Tasks 1-2.

**Files:**
- Create: `paper_trading/auth/service.py`
- Modify: `paper_trading/auth/__init__.py`
- Create: `test/paper_trading/auth/test_auth_service.py`

**Interfaces:**
- `normalize_email(email: str) -> str`
- `validate_password(password: str) -> None` raising `ValueError` with a safe policy message.
- `hash_password(password: str) -> str`
- `verify_password(password: str, password_hash: str) -> bool`
- `create_session_token(user_id: int, session_version: int, settings: AuthSettings, now: datetime | None = None) -> str`
- `decode_session_token(token: str, settings: AuthSettings, now: datetime | None = None) -> SessionClaims`
- `new_auth_token() -> tuple[str, str]` returning `(raw_token, token_hash)` and never persisting the raw value.
- `hash_auth_token(raw_token: str) -> str`
- `bump_session_version(user: User) -> int`
- `build_session_cookie(response: Response, token: str, settings: AuthSettings) -> None`
- `build_csrf_cookie(response: Response, csrf_token: str, settings: AuthSettings) -> None`
- `clear_auth_cookies(response: Response, settings: AuthSettings) -> None`

- [ ] **Step 1: Write failing primitive tests**

Cover `test_normalize_email_trims_and_lowercases`, `test_validate_password_rejects_short_missing_letter_and_missing_number`, `test_hash_password_never_equals_plaintext_and_verifies`, `test_session_token_contains_user_and_session_version`, `test_decode_session_token_rejects_expired_and_wrong_version_claims`, `test_new_auth_token_returns_only_hash_for_storage`, `test_session_cookie_has_httponly_lax_and_secure_attributes`, and `test_clear_auth_cookies_expires_session_and_csrf_cookies`.

- [ ] **Step 2: Run the primitive tests to verify they fail**

Run: `uv run pytest test/paper_trading/auth/test_auth_service.py -v`

Expected: FAIL because the helper functions and `SessionClaims`/`AuthSettings` types are absent.

- [ ] **Step 3: Implement normalization, password, token, JWT, and cookie helpers**

Use `argon2.PasswordHasher` for hashing/verification and catch verification failures as `False`; use `jwt.encode`/`jwt.decode` with an explicit algorithm, subject/user ID, session version, issued-at, and expiry; use cryptographically random bytes and a one-way digest for raw auth-token storage; use `secrets.token_urlsafe` for CSRF values. Keep all cookie flags centralized in the cookie builders.

- [ ] **Step 4: Run the primitive tests to verify they pass**

Run: `uv run pytest test/paper_trading/auth/test_auth_service.py -v`

Expected: PASS.

- [ ] **Step 5: Run static checks for the new package**

Run: `uv run ruff check paper_trading/auth test/paper_trading/auth/test_auth_service.py && uv run mypy paper_trading/auth`

Expected: PASS with no lint or type errors.

- [ ] **Step 6: Commit the primitive slice**

```bash
git add paper_trading/auth test/paper_trading/auth/test_auth_service.py
git commit -m "feat: add browser session authentication primitives"
```

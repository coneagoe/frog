# Task 1 Implementation Report

## Files changed

- `utility/proxy.py`
- `test/utility/test_proxy.py`

## Implementation

- Added provider selection through `PROXY_PROVIDER` with `auto`, `proxy_pool`, and `qingguo` modes.
- Added ProxyPool URL configuration through `PROXY_POOL_URL`, defaulting to `http://proxy_pool:5010`.
- Added ProxyPool allocation via `/get/`, including HTTPS request type, response validation, and normalized proxy mappings.
- Added `_delete_proxy_from_pool()` using the ProxyPool `/delete/` endpoint.
- Extracted Qingguo allocation into `_get_proxy_from_qingguo()` while preserving credential validation and URL escaping.
- Kept lowercase proxy environment variables cleared before allocation and set only after successful provider allocation.
- Preserved existing direct-first `change_proxy` decorator behavior.
- Added contract tests for pool-only operation without Qingguo credentials and malformed ProxyPool payloads.

## Design decisions

- Explicit `proxy_pool` mode does not inspect or require Qingguo credentials.
- Explicit `qingguo` mode retains the existing credential requirement and request contract.
- Default `auto` mode attempts ProxyPool first and falls back to Qingguo when the pool allocation fails.
- Provider attempts remain bounded by `max_attempts`; malformed pool responses are treated as failed allocations.

## Tests and validation

- `uv run pytest test/utility/test_proxy.py -v` — **12 passed**.
- `uv run ruff check utility/proxy.py test/utility/test_proxy.py` — **passed**.
- `uv run ruff format --check utility/proxy.py test/utility/test_proxy.py` — **passed**.
- `git diff --check` — **passed**.

## Commit

- `0c701a76ba8207847568b6ee21fe73a583da8c79` (`feat: add ProxyPool allocation fallback`)

## Concerns

- No known concerns for Task 1.

## Fix Round 1

### Changes

- Preserved the initial ProxyPool exception as diagnostic context when auto fallback fails through `RequestException`, `ValueError`, or another provider exception.
- Redacted proxy URL userinfo from provider exception diagnostics before logging.
- Added deterministic coverage for ProxyPool failure followed by successful Qingguo fallback, including returned mapping and provider-attempt order.
- Added failure-context coverage proving sanitized ProxyPool diagnostics are surfaced without credentials.

### Tests and validation

- `uv run pytest test/utility/test_proxy.py -v` — **14 passed**.
- `uv run ruff check utility/proxy.py test/utility/test_proxy.py` — **passed**.
- `uv run ruff format utility/proxy.py test/utility/test_proxy.py` — **passed**.
- `git diff --check` — **passed**.

### Commit

- `fix: preserve proxy fallback diagnostics`.

### Concerns

- No known concerns for this fix round.

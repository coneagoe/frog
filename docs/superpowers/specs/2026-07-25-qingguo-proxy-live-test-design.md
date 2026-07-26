# Qingguo proxy live test design

**Date:** 2026-07-25

## Goal

Provide an opt-in executable that verifies Qingguo username/password proxy connectivity with credentials supplied by the repository-root `.env` file, while using the same Baidu HTTPS endpoint for runtime proxy health checks.

## Scope

- Change the runtime health-check URL in `utility.proxy` to `https://www.baidu.com`.
- Add `tools/test_proxy.py` as a live network probe, invoked with `uv run tools/test_proxy.py`.
- Load `QG_PROXY_KEY` and `QG_PROXY_PWD` from the root `.env` file at runtime.
- Reuse `utility.proxy.get_proxy()` to acquire and validate the authenticated proxy while preserving its existing retry behavior.
- Verify the acquired proxy with `https://www.baidu.com` and display non-secret diagnostics.
- When a fetched proxy fails the runtime health check, log Qingguo's optional `proxy_ip` and required `server` (`IP:port`) for that attempt; never log the authenticated proxy URL, key, or password.

Out of scope: changes to proxy acquisition, Docker configuration, provider retries, and default pytest execution.

## Architecture

`utility.proxy.get_proxy()` validates candidate proxies through `https://www.baidu.com`. It retains the current bounded timeout and only installs the lowercase proxy environment variables after an HTTP 200 response.

For a health-check failure after a valid Qingguo response, the runtime warning includes the response's `proxy_ip` when it is a string and the parsed `server`. Provider-response and transport failures that have no usable address retain their existing diagnostics.

`tools/test_proxy.py` is a standalone operational script with a guarded `main()` entry point. It performs these steps:

1. Locate and load the repository-root `.env` values without logging credentials.
2. Require non-empty `QG_PROXY_KEY` and `QG_PROXY_PWD`; report a configuration error and exit non-zero if either is absent.
3. Call `utility.proxy.get_proxy()` to obtain an authenticated `requests` proxy mapping, including bounded allocation and health-check retries.
4. Request `https://www.baidu.com` through that mapping with a bounded timeout.
5. Require a successful HTTP response, then print the proxy server address and elapsed time without embedded credentials.

The script is intentionally separate from `test/utility/test_proxy.py`: the pytest suite remains deterministic and mocks network access, while this script requires valid local credentials, an available Qingguo proxy, and external network access.

## Failure behavior

- Missing `.env` file or required credentials: print a concise configuration error and exit non-zero.
- Proxy allocation failure: surface the existing helper's error without exposing credentials and exit non-zero.
- Request timeout, transport error, or non-success HTTP status: print a concise validation error and exit non-zero.
- Never print the constructed authenticated proxy URL, the key, or the password.

## Tests and verification

Add focused mocked unit tests for the runtime health-check URL and failed-attempt `proxy_ip`/`server` diagnostics, plus the script's `.env` loading, credential validation, success output, and failure paths. Do not make the live probe part of default pytest behavior.

Verification will run the new focused unit test module with `uv run pytest`, then run `uv run ruff check` on the added Python files. The user can run the live command separately with valid `.env` credentials.

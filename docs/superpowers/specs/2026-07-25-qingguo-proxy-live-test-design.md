# Qingguo proxy live test design

**Date:** 2026-07-25

## Goal

Provide an opt-in executable that verifies Qingguo username/password proxy connectivity with credentials supplied by the repository-root `.env` file.

## Scope

- Add `tools/test_proxy.py` as a live network probe, invoked with `uv run tools/test_proxy.py`.
- Load `QG_PROXY_KEY` and `QG_PROXY_PWD` from the root `.env` file at runtime.
- Reuse `utility.proxy.get_proxy()` to request the proxy address and preserve its existing retry behavior.
- Form the Qingguo documented HTTP proxy URL with the requested address and the environment credentials.
- Verify the proxy with `https://api.ipify.org?format=json` and display non-secret diagnostics.

Out of scope: changes to proxy acquisition, application runtime configuration, Docker configuration, provider retries, and default pytest execution.

## Architecture

`tools/test_proxy.py` is a standalone operational script with a guarded `main()` entry point. It performs these steps:

1. Locate and load the repository-root `.env` values without logging credentials.
2. Require non-empty `QG_PROXY_KEY` and `QG_PROXY_PWD`; report a configuration error and exit non-zero if either is absent.
3. Call `utility.proxy.get_proxy()` to obtain an `IP:port` address.
4. Construct `http://<key>:<password>@<IP>:<port>` and provide it as both the HTTP and HTTPS `requests` proxy values, matching the Qingguo Python example.
5. Request the ipify JSON endpoint with a bounded timeout, require a successful response and a non-empty string `ip` field, then print the egress IP, elapsed time, and address without embedded credentials.

The script is intentionally separate from `test/utility/test_proxy.py`: the pytest suite remains deterministic and mocks network access, while this script requires valid local credentials, an available Qingguo proxy, and external network access.

## Failure behavior

- Missing `.env` file or required credentials: print a concise configuration error and exit non-zero.
- Proxy allocation failure: surface the existing helper's error without exposing credentials and exit non-zero.
- Request timeout, transport error, non-success HTTP status, invalid JSON, or a response lacking a non-empty `ip`: print a concise validation error and exit non-zero.
- Never print the constructed authenticated proxy URL, the key, or the password.

## Tests and verification

Add focused mocked unit tests for the script's `.env` loading, credential validation, success output, and failure paths. Do not make the live probe part of default pytest behavior.

Verification will run the new focused unit test module with `uv run pytest`, then run `uv run ruff check` on the added Python files. The user can run the live command separately with valid `.env` credentials.

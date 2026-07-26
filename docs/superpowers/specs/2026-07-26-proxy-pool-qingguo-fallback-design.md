# ProxyPool Deployment with Qingguo Fallback

## Goal

Deploy `jhao104/proxy_pool` as a private, self-hosted source of best-effort public proxies for AkShare downloads. Keep Qingguo as an automatic fallback during the migration so AkShare jobs retain the current failure-recovery path.

## Scope

- Add a dedicated `proxy_pool` service and dedicated `proxy_redis` service to the existing Compose stack.
- Do not publish the ProxyPool API or its Redis port to the host network.
- Change only the proxy allocation path used by `utility.proxy` and the AkShare download retry path that already imports `change_proxy`.
- Add configuration to select `auto`, `proxy_pool`, or `qingguo` provider behavior.
- Update focused tests, the proxy diagnostic command, and deployment documentation.

## Non-Goals

- Do not route all application, Airflow, or Celery traffic through a proxy.
- Do not use the existing Celery Redis instance for ProxyPool state.
- Do not replace public proxies with a relay, add a public API, or guarantee IP geography, sticky sessions, or availability.
- Do not remove Qingguo credentials or code in this migration.

## Architecture

`proxy_pool` runs the official ProxyPool scheduler and HTTP API. It stores its state in `proxy_redis`. Both containers remain on the default Compose network and are addressed by service name. Only the project containers can access `http://proxy_pool:5010`; neither `5010` nor `6379` is published to the host.

Airflow and Celery retain their existing Redis and database dependencies. They receive `PROXY_POOL_URL=http://proxy_pool:5010` and `PROXY_PROVIDER=auto` through their existing common environment mappings. Their Compose dependencies include `proxy_pool` only where those services can execute AkShare downloads.

## Provider Selection

`utility.proxy` owns provider-specific allocation behind its existing `get_proxy()` public function.

- `auto` is the default migration mode. It first requests `GET /get/?type=https` from ProxyPool. If the API cannot be reached, returns no proxy, returns malformed data, or returns a proxy that fails the existing egress health check, it falls back to Qingguo.
- `proxy_pool` requests only ProxyPool. Allocation failure raises `ProxyError` after the existing bounded retry behavior.
- `qingguo` preserves the current Qingguo-only behavior.

The local endpoint returns an uncredentialed `host:port`; the application forms identical `http://host:port` values for the HTTP and HTTPS `requests` proxy mappings. The Qingguo adapter retains URL-escaped credential construction.

## Request and Failure Flow

The current `change_proxy` decorator remains limited to AkShare downloader functions. Its first attempt keeps direct connectivity behavior. On `ConnectionError` or `ProxyError`, it clears proxy environment variables, calls `get_proxy()`, waits, and retries with bounded attempts.

When ProxyPool supplies an endpoint, `utility.proxy` validates it through the existing egress check before installing `http_proxy` and `https_proxy`. A failed validation or a proxy transport failure triggers best-effort `GET /delete/?proxy=host:port`, so a known-bad endpoint is removed from the local pool. Failures in deletion are logged but never conceal the original allocation or request error.

Only transport/proxy failures cause eviction. Application-level responses, including valid HTTP error responses, do not automatically identify a proxy as bad.

## Security and Operations

ProxyPool and `proxy_redis` are private Compose services. The implementation does not expose `/all/`, `/pop/`, or `/delete/` outside the network; no host port mapping is added. ProxyPool uses a separate Redis volume/state from Airflow and Celery.

Public proxies are untrusted and must not carry credentials, cookies, tokens, or sensitive payloads. This deployment is for AkShare retrieval only. HTTPS is used for the target request where supported, but it does not make an arbitrary proxy trusted.

Pool occupancy is observable through `GET /count/`. A nonzero count is not proof of target-path availability; allocation retains the existing egress validation. Operators can keep `PROXY_PROVIDER=auto` while measuring success before switching to `proxy_pool` only.

## Testing and Verification

- Unit-test ProxyPool payload parsing, `host:port` proxy mapping, provider selection, fallback, malformed/empty responses, and best-effort eviction.
- Preserve the current Qingguo adapter tests and retry semantics.
- Update AkShare integration-style tests to verify proxy refresh remains bounded and provider failures remain isolated from non-proxy exceptions.
- Extend the diagnostic command to probe the selected provider without exposing credentials.
- Run `docker compose config` and start only `proxy_redis` and `proxy_pool`; verify that `http://proxy_pool:5010/count/` succeeds from an eligible project container and neither service publishes a host port.
- Run focused proxy and AkShare tests with `uv run pytest`.

## Rollout and Rollback

Deploy with `PROXY_PROVIDER=auto`. Monitor ProxyPool API reachability, pool count, allocation success, egress validation success, and AkShare request success. Change to `proxy_pool` only after the local pool is consistently effective. To roll back, set `PROXY_PROVIDER=qingguo` and restart the affected workers; this bypasses ProxyPool without removing the containers or Qingguo configuration.

## 1. Request body size cap (agent-orchestrator)

- [x] 1.1 Add `max_request_body_bytes` setting (default 8 MiB) + validator to `config.py`.
- [x] 1.2 Add `MaxBodySizeMiddleware` (pure ASGI) in `runtime/request_limits.py`.
- [x] 1.3 Wire it into `runtime/app.py` inside the CORS middleware.
- [x] 1.4 Unit tests: declared-oversize → 413, streamed-oversize (no Content-Length) → 413, within-limit passthrough, non-http passthrough.

## 2. RESP parser length bounds (dragncards-common)

- [x] 2.1 Bound `$`/`*` length prefixes (reject negative-except-`-1` and over-ceiling) in `resp.py::_read_resp`.
- [x] 2.2 Unit tests: oversized bulk, oversized array, negative bulk length all raise `RespError`.

## 3. RESP from_url latent TypeError (agent-orchestrator)

- [x] 3.1 Subclass `__init__` accepts optional `tracer`, defaulting to the module tracer.
- [x] 3.2 Unit tests: `from_url` on the subclass injects the default tracer and honors an explicit one.

## 4. Bifrost negative-cache TTL rounding (agent-orchestrator)

- [x] 4.1 Add `_ttl_int` so a positive TTL never rounds to `0`; use it for all cache-TTL ints.
- [x] 4.2 Remove the redundant `_unavailable_retryable_cache_ttl_seconds` instance field added by the prior change.

## 5. Dashboard CollapsibleCard simplification

- [x] 5.1 Remove the unused `defaultOpen` prop from `collapsible-card.tsx`.

## 6. Verification

- [x] 6.1 `./scripts/lint.sh --fix`, unit tests (all services + shared), integration tests all pass.
- [x] 6.2 Playwright: `/history` CollapsibleCard + RightDrawer still render/toggle.

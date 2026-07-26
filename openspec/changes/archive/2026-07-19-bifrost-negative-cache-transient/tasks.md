## 1. Retryable-aware negative TTL

- [x] 1.1 Add `unavailable_retryable_cache_ttl_seconds` (default 30.0) to
      `BifrostClient.__init__` and store its rounded int form.
- [x] 1.2 In `list_models`, when `_list_models_uncached` raises a `BifrostError`,
      select the negative-cache write TTL by `exc.retryable`: the short retryable
      TTL when retryable, the full TTL otherwise; only write when the chosen TTL
      is positive.
- [x] 1.3 Preserve existing behavior: successful listing clears the marker, the
      negative-read short-circuit is unchanged, and `clear_model_cache` still
      flushes positive and negative keys.

## 2. Configuration

- [x] 2.1 Add `bifrost_unavailable_retryable_cache_ttl_seconds` setting
      (env `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS`, default 30) with a
      positive-value validator, mirroring the existing unavailable-TTL setting.
- [x] 2.2 Wire the setting into `BifrostClient` construction in `runtime/app.py`.

## 3. Tests

- [x] 3.1 Unit test: a retryable failure (5xx/timeout) is negatively cached with
      the short retryable TTL, not the full definitive TTL.
- [x] 3.2 Unit test: a non-retryable failure (4xx auth) keeps the full TTL.
- [x] 3.3 `./scripts/lint.sh --fix` and `uv run pytest tests/unit` pass.

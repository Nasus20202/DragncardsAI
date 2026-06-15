## 1. Remove `/tools` endpoint

- [x] 1.1 Delete the `/tools` endpoint handler function (lines 590-615) from `services/game-service/src/game_service/api/routers/meta.py`

## 2. Clean up imports

- [x] 2.1 Remove unused `Client` import from `fastmcp` in `meta.py`
- [x] 2.2 Remove unused `escape` import from `html` in `meta.py`
- [x] 2.3 Remove unused `json` import in `meta.py`

## 3. Verify and test

- [x] 3.1 Run unit tests to ensure no breaking changes
- [x] 3.2 Run lint to verify code quality
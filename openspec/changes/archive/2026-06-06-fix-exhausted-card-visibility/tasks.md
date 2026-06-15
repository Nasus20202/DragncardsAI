## 1. Code Changes

- [x] 1.1 Remove rotation check from hidden card condition in `_simplify_marvel_state`
- [x] 1.2 Test that exhausted cards (Side B) are visible with correct `exhausted: true` field

## 2. Testing

- [x] 2.1 Add test case for exhausted card on Side B being visible (not hidden)
- [x] 2.2 Add test case for facedown card being hidden
- [x] 2.3 Update existing tests that incorrectly expect facedown behavior for exhaustion

## 3. Verification

- [x] 3.1 Run unit tests to verify changes
- [x] 3.2 Run integration tests to verify real DragnCards behavior
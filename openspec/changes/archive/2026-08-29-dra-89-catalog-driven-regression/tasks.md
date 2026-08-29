## 1. Catalog-driven regression

- [x] 1.1 Update the path-spelling regression to build its scenario and hero-deck selections from every entry returned by setup discovery, pass those exact IDs into creation, and assert opaque values; verify with the focused neutral-setup test.
- [x] 1.2 Preserve the raw-path rejection regression and confirm no runtime implementation files change; verify with the focused neutral-setup test and a diff inspection.

## 2. Specification and verification

- [x] 2.1 Record the unchanged-ID pass-through contract in the Marvel LCG delta spec; verify with `openspec validate dra-89-catalog-driven-regression --strict`.
- [x] 2.2 Run the game-service unit suite and `openspec validate --all`; verify all tests pass and no OpenSpec validation failures remain.

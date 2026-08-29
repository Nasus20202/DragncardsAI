## 1. Catalog identity resolution

- [x] 1.1 Add a bounded Marvel LCG document-path variant helper and build scenario/deck catalog maps with both leading-`./` spellings, preserving the live path as each map value; verify with focused platform tests.
- [x] 1.2 Keep explicit raw paths and unknown opaque ids rejected before table creation; verify no document or new-game request is made for each invalid-input case.

## 2. Regression coverage

- [x] 2.1 Add a regression test where setup discovery returns `./deck/starter/spider_man.json` and creation returns `deck/starter/spider_man.json`, asserting the reported opaque id resolves and the live path is fetched.
- [x] 2.2 Run the game-service unit and Marvel integration tests that cover setup catalog discovery and creation; record the singleton-engine limitation if a live integration cannot create a second game. (`15` focused setup tests and `594` game-service unit tests passed; the opt-in live integration was skipped because no live integration credentials were provided, and the shared engine already has an active singleton game.)

## 3. Repository specification

- [x] 3.1 Validate the OpenSpec change and archive it so the main Marvel LCG specification records cross-request catalog identity behavior.

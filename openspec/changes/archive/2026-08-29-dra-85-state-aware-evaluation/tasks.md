## 1. Authoritative Marvel evidence validation

- [x] 1.1 Add a side-effect-free validator for normalized Marvel move evidence that reads only authoritative `mode` and main-scheme `tokens.threat`, recognizes claimed threat removal conservatively, and leaves unavailable/raw/hidden facts unguessed.
- [x] 1.2 Apply the validator after judge parsing and before verdict write-back, forcing terminal loss transitions and unobserved threat-removal claims to override positive judge scores while preserving the existing verdict schema.
- [x] 1.3 Add focused deterministic tests covering a positive verdict followed by the authoritative 12/14→14/14 loss and a positive threat-removal claim with unchanged main-scheme threat.

## 2. Coordinator provenance and durable option identity

- [x] 2.1 Carry coordinator prompt text and server-set provenance (source, orchestrator session, parent job, and child job) on child agent history moves without changing legacy chat payloads.
- [x] 2.2 Assemble and render coordinator provenance as untrusted evidence, with deterministic source attribution when the supplied instruction conflicts with resulting state; preserve hidden-information boundaries.
- [x] 2.3 Persist the resolved Marvel option identity from the successful option listing, including top-level event metadata from the normalized options response, and retain legacy fallbacks for old rows.
- [x] 2.4 Add focused history/orchestrator and eval tests proving provenance attribution and durable `{id,name,event}` option identity persistence without reconstructing generic action names.

## 3. Specifications and proof

- [x] 3.1 Add complete capability deltas for `agent-move-evaluation` and `history-event-store`, including compatibility, provenance, terminal, and hidden-information scenarios.
- [x] 3.2 Run focused eval-service and orchestrator history tests plus OpenSpec validation; record exact commands and results.

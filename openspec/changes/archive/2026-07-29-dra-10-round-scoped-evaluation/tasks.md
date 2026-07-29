# Tasks

## 1. Reproduce and pin down the reported problems

- [x] 1.1 Confirm a multi-call play becomes several independent move targets:
      `RequestService._plan_moves` emits one `PlannedTarget` per `agent` event, so
      `move_card` / `exhaust_card` / `modify_tokens` of one play are three
      verdicts.
- [x] 1.2 Confirm the prompt never tells the judge a play spans calls: `RUBRIC`
      in `judge/prompt.py` asks `strategic_quality` and `tempo_efficiency` of the
      single move, and `_neighbour_block` says only "do not grade" the
      neighbours.
- [x] 1.3 Confirm the window ignores rounds: `_neighbour_window` in
      `judge/assembly.py` filters on `event.seq < target_seq` alone, so it crosses
      round boundaries in one direction and stops inside the round in the other.
- [x] 1.4 Confirm selecting a round requires a move: the only UI path to
      `scope=round` is `mode="selected"`, which submits `selection.seqs:
      [selectedSeq]`; `Selection.rounds` is accepted by the API and never sent.
- [x] 1.5 Confirm the parallelism bound is in-process: `EvaluationWorker`
      `_global_sem` plus the never-evicted `_game_sems` dict, at
      `EVAL_PER_GAME_CONCURRENCY` = 2.
- [x] 1.6 Record the base unit-test counts before changing anything: eval-service
      178 passed, dashboard 340 passed (54 files). game-service could not be
      baselined (384 collection errors from an unpopulated submodule, an
      environment fault fixed mid-task, not a code fault).
- [x] 1.7 Measure the payload delta with the REAL assembly + prompt code over a
      synthetic game shaped like the recorded ones (no recorded game is reachable
      without the Docker stack, which is prohibited for this change): the move
      prompt goes 5,553 -> 9,080 mean chars, **+63.5%**, still under a fifth of
      the pre-projection 13,750 tokens DRA-7 measured. The first harness run was
      wrong (the fixture omitted the `state` wrapper, so no round was detected and
      the projection saw nothing) and was corrected.

## 2. Round-scoped move context (judge input)

- [x] 2.1 Add `judge/rounds.py`: `display_round` / `round_label` for the
      round-of-play convention, `round_span_containing` over detected
      boundaries, and `neighbour_events` selecting the agent moves of a span on
      one side of a target. No import of `assembly`, so there is no cycle and
      `detect_round_boundaries` stays owned by its module.
- [x] 2.2 `MoveInput` gains `round_number` / `round_span`; `assemble_move_input`
      resolves the containing round and windows within it, falling back to the
      whole-timeline count window when no round contains the move.
- [x] 2.3 Keep skipped (non-strategic) actions IN the context window — they are
      skipped as targets, not as evidence of intent.
- [x] 2.4 Raise `EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` to 100/100 and
      redocument them as backstops rather than the mechanism; keep `_AFTER=0`
      working as the no-hindsight switch.
- [x] 2.5 Wire the round-scoped assembly through `Evaluator._produce_verdict`.

## 3. Round-aware grading instruction (judge prompt)

- [x] 3.1 Extend `RUBRIC` with the multi-call-play instruction: grade the move as
      the step it is within the play its round reveals, do not score down a
      necessary step for achieving nothing alone, do not charge one play against
      every action that makes it up.
- [x] 3.2 State the round of play in the move prompt and label the two context
      halves "earlier in this round" / "later in this round", keeping the
      existing not-hindsight warning on the later half.
- [x] 3.3 Use the round-of-play label in the round roll-up prompt too, so a
      judge is never shown a raw `roundNumber` of 0.

## 4. Round listing API

- [x] 4.1 Add `RoundSummary` / `RoundListResponse` to `schemas/api.py`.
- [x] 4.2 Add `runtime/rounds.py`: read the game's events once, expand detected
      boundaries into summaries with label, span, agent-move count and acting
      players; 404 on a game with no events.
- [x] 4.3 Add `GET /games/{game_id}/rounds` with the same `validate_game_id`
      hardening the other game routes use, plus the `get_rounds_service` dep.

## 5. Parallel evaluation bounded by durable state

- [x] 5.1 `Repository.claim_pending_targets` takes `global_limit` /
      `per_game_limit` and, inside the claiming transaction, counts `running`
      rows globally and per game so it claims only the remaining capacity.
- [x] 5.2 Delete `EvaluationWorker._global_sem` and `_game_sems`; pass the caps
      into the claim instead. No in-process structure bounds the work.
- [x] 5.3 Make `drain_once` report PROGRESS rather than rows claimed, so a cycle
      whose targets all re-deferred is an idle cycle and the worker waits.
- [x] 5.4 Raise `EVAL_PER_GAME_CONCURRENCY` 2 → 4; leave
      `EVAL_GLOBAL_CONCURRENCY` at 8 as the provider-stampede guard.

## 6. Evaluator version and verdict comparability

- [x] 6.1 `EVALUATOR_VERSION` default `eval-1` → `eval-2`, since the judge input
      and instruction both changed.
- [x] 6.2 Dashboard: read the evaluator version off a verdict and aggregate only
      the newest version on the scorecard, disclosing the excluded count.

## 7. Dashboard: one scope question and a real round picker

- [x] 7.1 Types + `listGameRounds` in `lib/eval-api.ts` for the new endpoint.
- [x] 7.2 Rebuild `EvaluationControl` around a single "What to evaluate" choice
      (Moves / Rounds / Whole game), each owning its own follow-up input.
- [x] 7.3 Round picker: checkbox list of the service-reported rounds, labelled
      "Round N · M moves · #from–#to", submitting `selection.rounds`.
- [x] 7.4 Rebuild every control on Hero UI / the shared field components; leave
      the error surface's semantics alone for DRA-18.
- [x] 7.5 Load the rounds when the panel opens for a game, with a disabled
      picker and an explanation when the game has no detectable round.

## 8. Tests

- [x] 8.1 `tests/unit/test_rounds.py` — round-of-play labels including
      `roundNumber` 0, span lookup, and neighbour selection within a span.
- [x] 8.2 `tests/unit/test_assembly.py` — the window covers the whole round both
      ways; never crosses into an adjacent round; keeps non-strategic moves as
      context; falls back to the count window with no detectable round; the
      backstop clips a long round from the near side.
- [x] 8.3 `tests/unit/test_judge.py` — the prompt names the round of play, labels
      the two halves, and carries the multi-call-play instruction.
- [x] 8.4 `tests/unit/test_api.py` — `GET /games/{id}/rounds` shape, labels, and
      404; a round-scope request naming only `rounds` expands to targets with no
      seq given.
- [x] 8.5 `tests/unit/test_worker_concurrency.py` — the claim respects the
      per-game and global caps from durable state; a many-target drain loses and
      duplicates nothing (every target terminal exactly once, one verdict each);
      an all-deferred cycle reports no progress.
- [x] 8.6 `tests/unit/test_config.py` — the new defaults.
- [x] 8.7 Dashboard: `evaluation-control.test.tsx` — a round is selectable with
      no move selected and submits `selection.rounds`; the whole-game choice
      ignores the transcript selection; range validation still holds.
- [x] 8.8 Dashboard: scorecard excludes older evaluator versions and says so.

## 9. Documentation and spec

- [x] 9.1 README "What the judge is sent" rewritten for the round window; config
      table rows updated; `.env.example` updated.
- [x] 9.2 Service `AGENTS.md`: the judge window is the round, and why the
      non-strategic taxonomy does not apply to context.
- [x] 9.3 Keep the surrounding files current: surface the parallel-evaluation and
      context knobs in `docker-compose.yaml` (they were not settable there at all,
      so the container silently used the code defaults) and update the root
      `README.md` architecture paragraph, whose description of what the
      eval-service grades this change makes stale. No new service, port, or
      required env var, so no script list changes; the Swagger index merges each
      service's live OpenAPI document, so the new route appears without an edit,
      and the dashboard proxy is path-agnostic so it needs no allowlist entry.
- [x] 9.4 `./scripts/lint.sh --fix`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration eval-service`, `openspec validate --all`.
- [x] 9.5 Rebased onto the integration branch three times as DRA-14, DRA-18,
      DRA-13, DRA-15 and DRA-17 landed. Audited every span / target-seq /
      created-count assertion in `tests/integration/test_worker_end_to_end.py`
      and `tests/unit/test_cascade.py`: this change moves no boundary (DRA-14
      owns that), so none needed updating, and both are green.
- [x] 9.6 Added two integration tests on real PostgreSQL for the durable
      concurrency claim, which is the only place ``FOR UPDATE SKIP LOCKED`` is
      exercised (sqlite omits it): the per-game cap holds across replicas, and a
      whole round drains in parallel losing and duplicating nothing.

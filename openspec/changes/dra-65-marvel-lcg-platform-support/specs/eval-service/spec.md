# eval-service

## ADDED Requirements

### Requirement: Platform is a stored column on evaluation requests and targets

`platform` SHALL be a real column on both `evaluation_requests` and `evaluated_targets`, declared `NOT NULL DEFAULT 'dragncards'`, so every evaluation the service has ever recorded is attributable to the platform whose recording it graded and every row written before this change reads as `dragncards` with no backfill.

The column SHALL be joined into the structures that key on the game today:

- `uq_targets_game_seq_scope_player` SHALL cover `(game_id, platform, target_seq, scope, player)`, so one recorded sequence on one platform is one target and the same identifier on the other platform is a different target rather than a constraint violation;
- the `ix_*_game_id` index on `evaluation_requests` and the `ix_*_game_id` index on `evaluated_targets` SHALL each be scoped to the platform alongside the game, so a per-game read stays a single index lookup after the filter gains a column.

The platform of a request SHALL be RESOLVED from the recorded history the request targets, not trusted from the caller: the service reads which platform produced that game's events and stores that value on the request and on every target the request expands to. A request body that names a platform disagreeing with the recording SHALL be refused with a `422` naming the conflict rather than evaluating a recording under a label that is not its own. Every target of one request SHALL carry that one platform.

A request for a game whose recorded history the service cannot attribute to a known platform SHALL be treated as `dragncards`, consistent with the history store's own default, so a recording made before the discriminator existed remains evaluable.

#### Scenario: A request stores the platform of the recording it grades

- **WHEN** an evaluation is requested for a game whose recorded events were produced on `marvel-lcg`
- **THEN** the stored `evaluation_requests` row and every `evaluated_targets` row it expands to SHALL carry `platform` `marvel-lcg`

#### Scenario: A pre-existing row reads as dragncards

- **WHEN** the migration is applied to a database holding evaluation requests and targets written before this change
- **THEN** every existing row SHALL read `platform` `dragncards`
- **AND** no backfill statement SHALL be required for them to do so

#### Scenario: The same sequence on two platforms is two targets

- **WHEN** a target exists for `(game_id, target_seq, scope, player)` on `dragncards` and the same tuple is claimed for `marvel-lcg`
- **THEN** both targets SHALL be stored and evaluated independently
- **AND** a second claim of either tuple within its own platform SHALL still be de-duplicated by the unique constraint

#### Scenario: A caller-named platform that contradicts the recording is refused

- **WHEN** a request names a platform that is not the platform of the game's recorded history
- **THEN** the service SHALL answer `422` naming the conflict
- **AND** SHALL NOT create the evaluation

#### Scenario: An unattributable recording is evaluated as dragncards

- **WHEN** an evaluation is requested for a game whose recorded events carry no platform
- **THEN** the service SHALL evaluate it with `platform` `dragncards`

### Requirement: The verdict idempotency key gains the platform without re-keying existing verdicts

The verdict idempotency key SHALL identify a verdict by the platform as well as the game, so two platforms' recordings of the same identifier and sequence cannot collapse into one stored verdict.

The key's existing components and their order SHALL be unchanged, and the platform SHALL be APPENDED as a trailing component that is present only when the platform is not the default. A verdict on `dragncards` SHALL therefore produce a byte-identical key to the one it produced before this change, so no previously written verdict is re-keyed, no verdict is re-evaluated because its digest moved, and an idempotent re-request still de-duplicates against the verdict already in history.

A recording with no platform recorded SHALL be keyed as `dragncards`, so the absence of the field and the default value are the same key rather than two.

This rule SHALL be asserted by a test that pins the key produced for a `dragncards` verdict against the key the previous implementation produced, because a change to this string is invisible at runtime and only shows up as a duplicated or a lost verdict.

#### Scenario: A dragncards verdict keeps its existing key

- **WHEN** the idempotency key is computed for a verdict on a `dragncards` recording
- **THEN** it SHALL equal the key the previous implementation produced for the same game, sequence, scope, player, evaluator version and judge configuration
- **AND** re-requesting that evaluation SHALL still be de-duplicated rather than written a second time

#### Scenario: A marvel-lcg verdict gets a distinct key

- **WHEN** verdicts are written for the same game identifier, sequence, scope and player on `dragncards` and on `marvel-lcg`
- **THEN** the two keys SHALL differ
- **AND** both verdicts SHALL be stored rather than one overwriting or de-duplicating the other

#### Scenario: An absent platform keys as the default

- **WHEN** the idempotency key is computed for a recording that carries no platform
- **THEN** it SHALL equal the key computed for the same target on `dragncards`

### Requirement: The platform migration is dialect-paired and safe for the shared runner

The schema change SHALL be delivered as the next migration version in BOTH dialects the shared runner discovers — `0004_<name>.postgresql.sql` and `0004_<name>.sqlite.sql` — because the runner globs `*.sql`, takes the pre-`.` prefix as the version, and sorts lexicographically, so a zero-padded pair is what makes the ordering and the dialect selection work.

Neither file SHALL contain a semicolon inside a string literal or inside a `DO $$ … $$` block, because the shared runner splits a script on a naive `;` and would execute the fragments as separate statements.

The SQLite variant SHALL widen `uq_targets_game_seq_scope_player` with the table-rebuild pattern already used by `0002_target_player.sqlite.sql` — create the replacement table with the widened constraint, copy the rows, drop the original, rename — because SQLite cannot drop or alter a constraint in place.

Applying either variant to a database holding existing evaluations SHALL leave every stored request, target, status, attempt count and verdict readable and unchanged apart from reading `platform` `dragncards`.

#### Scenario: Both dialects are present at the same version

- **WHEN** the migration directory is listed
- **THEN** it SHALL contain `0004_<name>.postgresql.sql` and `0004_<name>.sqlite.sql`
- **AND** the runner SHALL select the file matching the connected dialect

#### Scenario: A statement is not split in the middle

- **WHEN** either migration file is read by the shared runner's statement splitter
- **THEN** every produced fragment SHALL be a complete, executable statement
- **AND** no fragment SHALL be produced by a semicolon inside a string literal or a `DO $$ … $$` block

#### Scenario: SQLite rebuilds the targets table to widen the constraint

- **WHEN** the SQLite migration widens `uq_targets_game_seq_scope_player`
- **THEN** it SHALL create the replacement table, copy every row, drop the original, and rename the replacement
- **AND** every target's status, attempt count and verdict SHALL read back identically afterwards

#### Scenario: An existing evaluation survives the migration

- **WHEN** the migration is applied to a database holding completed evaluations of a DragnCards game
- **THEN** those requests and targets SHALL still be readable with their verdicts
- **AND** they SHALL read `platform` `dragncards`

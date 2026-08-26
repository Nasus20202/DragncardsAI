# Seat-scoped simplified state projection

## MODIFIED Requirements

### Requirement: Per-seat hidden information is honoured per platform and collapses to the existing HIDDEN form

The projection SHALL be produced for a READING SEAT, and SHALL contain exactly the
information that seat's human player would see. A card the reading seat cannot see SHALL
be reported only as a count under the existing `HIDDEN` form and SHALL NOT be reported by
name, identifier, type, or any other attribute.

On marvel-lcg the visibility decision SHALL be taken from the platform's own per-seat
model rather than from a card-back heuristic. For cards outside a `hand_cards` area, a
card SHALL be treated as hidden from the reading seat when the reading seat is not listed
in that card's `visible_for_players`, when `is_face_up` is not the real boolean `true`,
or when the card is one of another card's `down_card_ids`. For a card in the reading
seat's own `hand_cards` area, the engine ACL SHALL authorize its name and identifier;
`is_face_up` SHALL NOT be required to be true because the Marvel engine reports hand cards
as face down. A card in another player's hand SHALL remain hidden even if its ACL also
lists the reading seat. Missing, malformed, or ambiguous ACL metadata SHALL fail closed.
The normaliser SHALL NOT widen visibility because the world payload happens to contain a
card — marvel-lcg filters by card, not by the requesting seat, so the payload the
reading-seat projection is built from can contain a card only another seat can see.

On DragnCards the existing face-down and player/encounter-identity rules SHALL continue
to decide visibility, and supplying the ignored `player_n` selector SHALL NOT change its
existing state-cache behavior.

#### Scenario: A card another seat holds is a count, not a name

- **WHEN** a marvel-lcg world payload contains a card whose `visible_for_players` does not include the reading seat
- **THEN** that card SHALL appear in its zone only as part of a `HIDDEN` entry with a stack size
- **AND** its name and card identifier SHALL NOT appear anywhere in the projection

#### Scenario: An owner ACL reveals a Marvel hand card despite the face-down flag

- **WHEN** a card in the reading seat's own `hand_cards` area has an engine ACL containing that seat and reports `is_face_up` as `false`
- **THEN** it SHALL be projected with its name and identifier for the owner

#### Scenario: Another seat and a spectator cannot read an owner's hand card

- **WHEN** a Marvel hand card's ACL contains only its owner's seat
- **THEN** a projection requested by another seat SHALL include only a hidden count for that card
- **AND** a projection without `player_n` SHALL include only a hidden count for that card

#### Scenario: A face-down card is hidden even from the seat that owns the zone

- **WHEN** a marvel-lcg card outside a hand in the reading seat's own zone reports `is_face_up` false
- **THEN** it SHALL be projected as `HIDDEN`

#### Scenario: Cards tucked under another card are hidden

- **WHEN** a marvel-lcg card lists other cards in its `down_card_ids`
- **THEN** those cards SHALL be projected as `HIDDEN` and SHALL NOT be emitted as separate named entries

#### Scenario: Hidden cards of one zone merge into one entry

- **WHEN** several cards in one marvel-lcg zone are hidden from the reading seat
- **THEN** they SHALL be merged into a single `HIDDEN` entry whose `stackSize` is their total count, exactly as DragnCards hidden cards are merged

#### Scenario: A spectator sees only unambiguous public cards

- **WHEN** a two-seat Marvel state is normalized without `player_n`
- **THEN** every player hand SHALL contain only hidden counts
- **AND** a shared card SHALL remain named only when its ACL is visible to every represented engine seat

#### Scenario: Malformed ACL metadata is hidden

- **WHEN** a card has missing, non-integer, out-of-range, or otherwise malformed `visible_for_players` metadata
- **THEN** the normalizer SHALL emit that card only as `HIDDEN`
- **AND** SHALL NOT emit its name, identifier, type, or other card metadata

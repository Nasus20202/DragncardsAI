# Testing additions for Marvel setup integrity

## ADDED Requirements

### Requirement: Marvel setup integrity has focused regression coverage

The game-service test suite SHALL cover both a selected setup world that passes integrity
validation and a mismatched/default world that fails before session readiness. It SHALL also
cover an empty-pending render frame being acknowledged and followed by a later pending-seat
frame without fabricating an option.

#### Scenario: Focused Marvel tests cover setup and reveal liveness

- **WHEN** the focused Marvel driver tests run
- **THEN** they SHALL exercise selected setup validation, mismatch rejection, empty-reveal
  acknowledgement, and bounded acknowledgement degradation

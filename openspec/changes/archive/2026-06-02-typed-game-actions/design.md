## Context

Game actions are currently exposed through a generic `execute_action` entry point that requires consumers to inspect available actions and manually build payloads. This makes action usage noisy for LLM agents and spreads request-shape knowledge throughout the codebase. The proposal introduces typed helpers for each action, with explicit request/response models, while keeping the existing generic interface for backward compatibility.

## Goals / Non-Goals

**Goals:**
- Provide typed helper functions for each supported action in `game_actions.py`.
- Define request/response models per action to validate inputs and improve tooling.
- Preserve the existing `execute_action` and `get_session_actions` interfaces.
- Keep action definitions aligned with the DragnCards action schemas returned by the backend.

**Non-Goals:**
- Changing DragnCards backend behavior or action schemas.
- Removing or deprecating the generic `execute_action` interface.
- Introducing new action types beyond those already exposed by DragnCards.

## Decisions

- **Decision:** Implement typed action helpers in `game_actions.py` with one function per action type, each accepting a pydantic request model and returning a typed response model, written explicitly (not dynamically generated).
  **Alternatives considered:**
  - Continue using a single generic `execute_action` function. Rejected because it perpetuates manual payload construction and weak validation.
  - Generate helpers dynamically from the runtime schema. Rejected because it adds runtime complexity, obscures explicit action coverage, and can drift from static typing expectations in tooling.

- **Decision:** Mirror the action schema fields from `get_session_actions` into request/response models, including defaults and optional fields.
  **Alternatives considered:**
  - Use loose dicts with ad-hoc validation. Rejected due to inconsistent validation and limited documentation value.
  - Define a single union model for all actions. Rejected because per-action helpers are clearer for agent tooling and avoid large discriminated unions in call sites.

- **Decision:** Keep the underlying execution path via the existing `execute_action` implementation, wrapping it in typed helpers.
  **Alternatives considered:**
  - Add a new execution endpoint per action. Rejected because it increases surface area and duplicates execution plumbing without clear benefit.

## Risks / Trade-offs

- [Risk] DragnCards action schemas may change and drift from the typed models. → Mitigation: document schema update workflow and add tests/fixtures that validate model alignment with `get_session_actions` output.
- [Risk] Action coverage mismatch between typed helpers and runtime availability. → Mitigation: include a fallback helper for raw actions and ensure action enumeration tests track coverage.
- [Trade-off] Static models increase maintenance cost when new actions are added. → Mitigation: keep models close to schema definitions and add minimal generation helpers for updates.

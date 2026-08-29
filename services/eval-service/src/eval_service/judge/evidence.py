"""Deterministic checks for high-impact Marvel evaluation evidence.

The judge is useful for strategy and rules interpretation, but it is not the
source of truth for a state transition. This module applies the small set of
checks that must remain authoritative even when judge prose is stale or
confidently wrong.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from eval_service.judge.assembly import MoveInput
from eval_service.schemas.history import PLATFORM_MARVEL_LCG
from eval_service.schemas.verdict import VerdictPayload, VerdictScores

_TERMINAL_MODES = frozenset({"win", "loss"})
_THREAT_REMOVAL_RE = re.compile(
    r"(?:\b(?:remove|removes|removed|removing|reduc(?:e|es|ed|ing)|"
    r"lower(?:s|ed|ing)?|decreas(?:e|es|ed|ing)|clear(?:s|ed|ing)?|"
    r"thwart(?:s|ed|ing)?|prevent(?:s|ed|ing)?|take)\b[^\n]{0,80}\bthreat\b|"
    r"\bthreat\b[^\n]{0,80}\b(?:remove|reduc|lower|decreas|clear|"
    r"thwart|prevent)\w*\b|\bthwart(?:s|ed|ing)?\b)",
    re.IGNORECASE,
)
_MAIN_SCHEME_RE = re.compile(r"\bmain(?:[\s-]+scheme)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class MarvelStateEvidence:
    """Public authoritative facts extracted from one normalized Marvel state."""

    mode: str | None
    main_scheme_threat: int | None


def validate_marvel_move_verdict(
    verdict: VerdictPayload,
    move: MoveInput,
) -> VerdictPayload:
    """Apply authoritative Marvel evidence to a parsed move verdict.

    A missing or unrecognised state is deliberately a no-op. The evaluator never
    infers a card effect from raw engine data, a hidden card, or a guessed default.
    The returned model is a copy, so a caller can safely retain the judge's raw
    result for logging while writing only the corrected verdict.
    """
    if move.platform != PLATFORM_MARVEL_LCG:
        return verdict

    prior = _state_evidence(move.prior_state)
    resulting = _state_evidence(move.resulting_state)
    if prior is None and resulting is None:
        return verdict

    flags = list(verdict.flags)
    rationale = verdict.rationale.strip()
    scores = verdict.scores
    overall_score = verdict.overall_score

    resulting_mode = resulting.mode if resulting is not None else None
    if resulting_mode == "loss":
        scores = VerdictScores(
            rules_legality=0,
            strategic_quality=0,
            tempo_efficiency=0,
            threat_resource=0,
        )
        overall_score = 0
        _add_flag(flags, "terminal_loss")
        rationale = _append_reason(
            rationale,
            "Authoritative resulting state reports a terminal loss; positive "
            "judge reasoning cannot override that outcome.",
        )
    elif resulting_mode == "win":
        _add_flag(flags, "terminal_win")
        rationale = _append_reason(
            rationale,
            "Authoritative resulting state reports a terminal win.",
        )

    player_claims_threat = _claims_threat_removal(move)
    coordinator_claims_threat = _claims_threat_removal_from_coordinator(move)
    if (
        prior is not None
        and resulting is not None
        and prior.main_scheme_threat is not None
        and resulting.main_scheme_threat is not None
        and prior.main_scheme_threat == resulting.main_scheme_threat
    ):
        if player_claims_threat:
            # An action whose claimed public effect did not occur cannot receive any
            # credit for the move. This intentionally affects only the move after
            # both states and the claim are independently available.
            scores = scores.model_copy(update={"threat_resource": 0})
            overall_score = 0
            _add_flag(flags, "unobserved_threat_removal")
            rationale = _append_reason(
                rationale,
                "The authoritative main-scheme threat is unchanged, so the claimed "
                "threat-removal effect was not observed.",
            )
            if coordinator_claims_threat:
                _add_flag(flags, "coordinator_instruction_conflict")
                rationale = _append_reason(
                    rationale,
                    "The conflicting effect was supplied by the coordinator prompt, "
                    "not established by the player's own reasoning.",
                )
    return verdict.model_copy(
        update={
            "scores": scores,
            "overall_score": overall_score,
            "rationale": rationale,
            "flags": flags,
        }
    )


def _state_evidence(state: Any) -> MarvelStateEvidence | None:
    """Read only the DRA-83 normalized, visibility-safe state shape."""
    if not _is_normalized_state(state):
        return None
    mode = state.get("mode")
    normalized_mode = mode.strip().lower() if isinstance(mode, str) else None
    if normalized_mode not in _TERMINAL_MODES:
        normalized_mode = normalized_mode or None
    return MarvelStateEvidence(
        mode=normalized_mode,
        main_scheme_threat=_main_scheme_threat(state),
    )


def _is_normalized_state(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    return (
        isinstance(state.get("playRound"), int)
        and not isinstance(state.get("playRound"), bool)
        and isinstance(state.get("phase"), str)
        and isinstance(state.get("phaseLabel"), str)
        and isinstance(state.get("players"), dict)
        and isinstance(state.get("zones"), dict)
    )


def _main_scheme_threat(state: dict[str, Any]) -> int | None:
    zones = state.get("zones")
    if not isinstance(zones, dict):
        return None
    cards = zones.get("sharedMainScheme")
    if not isinstance(cards, list) or not cards:
        return None
    card = cards[0]
    if not isinstance(card, dict) or card.get("name") in (None, "HIDDEN"):
        return None
    tokens = card.get("tokens")
    if not isinstance(tokens, dict):
        return None
    value = tokens.get("threat")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value)
    return None


def _claims_threat_removal(move: MoveInput) -> bool:
    values = (move.intended_action, move.arguments, move.reasoning)
    return any(_claims_main_scheme_threat_removal(value) for value in values)


def _claims_main_scheme_threat_removal(value: Any) -> bool:
    text = _text(value)
    return (
        _THREAT_REMOVAL_RE.search(text) is not None
        and _MAIN_SCHEME_RE.search(text) is not None
    )


def _coordinator_instruction_text(prompt: Any) -> str:
    """Extract coordinator-authored text, stripping embedded engine prompts and checkpoints."""
    raw = _text(prompt)
    if not raw:
        return ""
    lines: list[str] = []
    in_engine_prompt = False
    in_checkpoint = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("CURRENT ENGINE PROMPT"):
            in_engine_prompt = True
            in_checkpoint = False
            continue
        if stripped.startswith("AUTHORITATIVE STATE CHECKPOINT"):
            in_checkpoint = True
            in_engine_prompt = False
            continue
        if stripped.startswith(
            (
                "PLAYER TURN REQUEST",
                "INSTRUCTIONS",
                "COORDINATOR INSTRUCTIONS",
                "RULES",
                "NOTES",
            )
        ):
            in_engine_prompt = False
            in_checkpoint = False

        if not in_engine_prompt and not in_checkpoint:
            lines.append(line)
    return "\n".join(lines)


def _claims_threat_removal_from_coordinator(move: MoveInput) -> bool:
    provenance = move.prompt_provenance
    if not isinstance(provenance, dict):
        return False
    if provenance.get("source") != "coordinator":
        return False
    instruction = provenance.get("instruction")
    if instruction is not None:
        return _claims_main_scheme_threat_removal(instruction)
    prompt = provenance.get("prompt")
    return _claims_main_scheme_threat_removal(_coordinator_instruction_text(prompt))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError, ValueError:
        return str(value)


def _add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _append_reason(existing: str, addition: str) -> str:
    if not existing:
        return addition
    return f"{existing} {addition}"

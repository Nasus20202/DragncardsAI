"""The shared Marvel Champions reference corpus has no platform contract."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SHARED_SKILL_DIRECTORIES = (
    REPO_ROOT / "skills" / "marvel-champions-rules-reference" / "resources",
    REPO_ROOT / "skills" / "marvel-champions-learn-to-play" / "references",
)
MARVEL_COORDINATOR_LOOP = (
    REPO_ROOT
    / "skills"
    / "marvel-champions-orchestrator"
    / "references"
    / "marvel-lcg-round-loop.md"
)
PLAYER_SKILL_FILES = (
    REPO_ROOT / "skills" / "marvel-champions-play" / "SKILL.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "tool-reference.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "reading-state.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "strategy.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "recovery.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "play-recipes.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "references" / "marvel-lcg.md",
    REPO_ROOT / "skills" / "marvel-champions-play" / "references" / "dragncards.md",
)
PLATFORM_TOKENS = (
    "DragnCards",
    "marvel-lcg",
    "DragnLang",
    "game-service_",
    "playerN",
    "stepId",
    "sharedMainScheme",
    "session_id",
    "raw_action",
)


def test_shared_rules_and_learning_references_are_platform_neutral() -> None:
    violations: list[str] = []
    for directory in SHARED_SKILL_DIRECTORIES:
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for token in PLATFORM_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)}: {token}")

    assert (
        not violations
    ), "platform tokens found in shared skill references: " + ", ".join(violations)


def test_marvel_coordinator_delegates_option_tools_to_the_seat_agent() -> None:
    text = MARVEL_COORDINATOR_LOOP.read_text(encoding="utf-8")

    assert "The coordinator observes" in text
    assert "does not call `list_game_options` or `choose_game_option` itself" in text
    assert "The seat agent calls `list_game_options`" in text
    assert "`choose_game_option`" in text


def test_player_skill_scopes_every_state_read_to_the_assigned_seat() -> None:
    for path in PLAYER_SKILL_FILES:
        text = path.read_text(encoding="utf-8")
        assert "player_n" in text, path
        assert "assigned" in text, path

    skill = PLAYER_SKILL_FILES[0].read_text(encoding="utf-8")
    assert "get_game_state(session_id, player_n=<your assigned seat>)" in skill
    assert "omitting it requests the spectator/public projection" in skill

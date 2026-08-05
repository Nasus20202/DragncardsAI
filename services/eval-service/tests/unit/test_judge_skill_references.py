"""The judge can be given a skill's reference files, and only its own.

Two things are pinned here. First that a selected reference actually reaches the
judge's system prompt -- before DRA-41 the resolver could not read a reference at
all, so a judge pointed at ``marvel-champions-rules-reference`` graded against
6.7% of the rulebook it was handed. Second that a caller-supplied reference path
cannot be walked out of its own skill directory, which is the price of taking a
path from an API caller at all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval_service.config import Settings
from eval_service.judge.assembly import MoveInput
from eval_service.judge.config import (
    ResolvedJudgeConfig,
    ResolvedReasoning,
    SkillReferenceBudgetError,
    SkillReferenceError,
    SkillResolver,
    UnknownSkillError,
    resolve_judge_config,
)
from eval_service.judge.prompt import (
    RUBRIC,
    build_game_messages,
    build_move_messages,
    build_round_messages,
)
from eval_service.judge.reference_budget import (
    UNCLIPPED_TEXT_PROJECTION_CHARS,
    ReferenceBudget,
    reference_budget,
)
from eval_service.judge.writeback import judge_config_digest
from eval_service.schemas.api import JudgeConfig


def _settings(**overrides) -> Settings:
    base = dict(eval_judge_model="anthropic/claude-default", eval_judge_provider="")
    base.update(overrides)
    return Settings(**base)


def _make_skill(root: Path, name: str, body: str = "body") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\n---\n{body}\n", encoding="utf-8"
    )
    return skill_dir


def _make_reference(skill_dir: Path, relative: str, body: str) -> Path:
    path = skill_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _resolver(tmp_path: Path) -> SkillResolver:
    return SkillResolver((tmp_path,))


def _budget(cap_chars: int = 0, **settings_overrides) -> ReferenceBudget:
    """A budget for tests that are about RESOLUTION rather than sizing.

    ``cap_chars=0`` is the default: no operator cap, so the budget is whatever
    the context window leaves (~340k chars at the default settings), which every
    fixture file in this module fits inside many times over.
    """
    return reference_budget(
        _settings(eval_judge_max_skill_reference_chars=cap_chars, **settings_overrides)
    )


#: The repo's shared ``skills/`` directory -- the same root the service resolves
#: against in the dev layout (``services/eval-service/tests/unit/x.py`` -> repo).
SHIPPED_SKILL_ROOT = Path(__file__).resolve().parents[4] / "skills"


def _shipped_skill(name: str) -> Path:
    path = SHIPPED_SKILL_ROOT / name
    if not (path / "SKILL.md").is_file():
        pytest.skip(f"shipped skill {name!r} not present at {SHIPPED_SKILL_ROOT}")
    return path


def _move() -> MoveInput:
    return MoveInput(
        game_id="g1",
        target_seq=2,
        intended_action="play",
        reasoning="",
        arguments={},
        prior_state={},
        resulting_state={},
    )


# --------------------------------------------------------------------------
# The defect: a reference reaches the judge
# --------------------------------------------------------------------------


def test_a_selected_reference_reaches_the_judge_prompt(tmp_path):
    """Fails without DRA-41: the resolver had no way to read a reference file."""
    skill = _make_skill(tmp_path, "rules", "SKILLBODY-AAA")
    _make_reference(skill, "resources/errata.md", "ERRATABODY-ZZZ")

    resolver = _resolver(tmp_path)
    skills = resolver.load_markdown(("rules",))
    references = resolver.load_references(
        ("rules/resources/errata.md",), budget=_budget()
    )

    system = build_move_messages(_move(), skills=skills, skill_references=references)[
        0
    ]["content"]
    assert "SKILLBODY-AAA" in system
    assert "ERRATABODY-ZZZ" in system
    assert "## Skill: rules" in system
    assert "### Reference: resources/errata.md" in system


def test_a_reference_is_selectable_without_its_skill(tmp_path):
    skill = _make_skill(tmp_path, "rules", "SKILLBODY-AAA")
    _make_reference(skill, "resources/errata.md", "ERRATABODY-ZZZ")

    references = _resolver(tmp_path).load_references(
        ("rules/resources/errata.md",), budget=_budget()
    )
    system = build_move_messages(_move(), skills=[], skill_references=references)[0][
        "content"
    ]
    assert "ERRATABODY-ZZZ" in system
    assert "SKILLBODY-AAA" not in system
    # The heading must not imply the judge holds the whole skill.
    assert "## Skill: rules (references only)" in system


def test_references_group_under_their_own_skill(tmp_path):
    rules = _make_skill(tmp_path, "rules", "RULES-BODY")
    play = _make_skill(tmp_path, "play", "PLAY-BODY")
    _make_reference(rules, "a.md", "RULES-REF")
    _make_reference(play, "b.md", "PLAY-REF")

    resolver = _resolver(tmp_path)
    system = build_move_messages(
        _move(),
        skills=resolver.load_markdown(("rules", "play")),
        skill_references=resolver.load_references(
            ("play/b.md", "rules/a.md"), budget=_budget()
        ),
    )[0]["content"]

    # Each reference sits under the skill it belongs to, not wherever it was
    # listed in the request.
    assert system.index("RULES-BODY") < system.index("RULES-REF")
    assert system.index("RULES-REF") < system.index("PLAY-BODY")
    assert system.index("PLAY-BODY") < system.index("PLAY-REF")


@pytest.mark.parametrize(
    "build",
    [
        lambda **kw: build_move_messages(_move(), **kw),
        lambda **kw: build_round_messages(_round_input(), **kw),
        lambda **kw: build_game_messages(_game_input(), **kw),
    ],
    ids=["move", "round", "game"],
)
def test_every_scope_carries_references(tmp_path, build):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "faq.md", "FAQBODY-QQQ")
    references = _resolver(tmp_path).load_references(
        ("rules/faq.md",), budget=_budget()
    )
    assert "FAQBODY-QQQ" in build(skill_references=references)[0]["content"]


def _round_input():
    from eval_service.judge.assembly import RoundInput

    return RoundInput(game_id="g1", target_seq=9, from_seq=1, to_seq=9, round_number=1)


def _game_input():
    from eval_service.judge.assembly import GameInput

    return GameInput(game_id="g1", target_seq=9, from_seq=1, to_seq=9)


def test_a_duplicated_selection_is_inlined_and_charged_once(tmp_path):
    """Naming a file twice must not double its block or its budget cost."""
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "errata.md", "E" * 4_000)

    loaded = _resolver(tmp_path).load_references(
        ("rules/errata.md", "rules/errata.md"), budget=_budget(6_000)
    )
    assert len(loaded) == 1

    system = build_move_messages(_move(), skills=[], skill_references=loaded)[0][
        "content"
    ]
    assert system.count("### Reference: errata.md") == 1


def test_a_selected_skill_and_a_references_only_skill_both_render(tmp_path):
    """The pop-then-trailing-loop split: exercise both halves in one prompt."""
    rules = _make_skill(tmp_path, "rules", "RULES-BODY")
    extra = _make_skill(tmp_path, "extra", "EXTRA-BODY")
    _make_reference(rules, "a.md", "RULES-REF")
    _make_reference(extra, "b.md", "EXTRA-REF")

    resolver = _resolver(tmp_path)
    system = build_move_messages(
        _move(),
        # Only ``rules`` has its SKILL.md selected; ``extra`` contributes a
        # reference alone.
        skills=resolver.load_markdown(("rules",)),
        skill_references=resolver.load_references(
            ("rules/a.md", "extra/b.md"), budget=_budget()
        ),
    )[0]["content"]

    assert "## Skill: rules\n" in system
    assert "## Skill: extra (references only)" in system
    assert "EXTRA-BODY" not in system
    # Order: the inlined skill and its own reference come before the
    # references-only block.
    assert (
        system.index("RULES-BODY")
        < system.index("RULES-REF")
        < system.index("EXTRA-REF")
    )


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reference",
    [
        "/etc/passwd",
        "/tmp/outside.md",
        "../outside.md",
        "../../outside.md",
        "resources/../../outside.md",
        # Canonical-form rules: resolves inside, but is not how the file is named.
        "resources/../resources/errata.md",
        "./resources/errata.md",
        # Not markdown, a directory, and the skill's own summary.
        "resources/notes.txt",
        "resources",
        "SKILL.md",
        # Simply absent.
        "resources/missing.md",
    ],
)
def test_a_reference_outside_its_skill_is_refused(tmp_path, reference):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "resources/errata.md", "INSIDE")
    (skill / "resources" / "notes.txt").write_text("not markdown", encoding="utf-8")
    (tmp_path / "outside.md").write_text("OUTSIDE-SECRET", encoding="utf-8")

    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references((f"rules/{reference}",), budget=_budget())


def test_a_symlink_out_of_the_skill_is_refused(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    secret = tmp_path / "secret.md"
    secret.write_text("OUTSIDE-SECRET", encoding="utf-8")
    (skill / "resources").mkdir()
    (skill / "resources" / "leak.md").symlink_to(secret)

    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references(
            ("rules/resources/leak.md",), budget=_budget()
        )


def test_a_symlinked_directory_component_is_refused(tmp_path):
    """The escape must be blocked mid-path, not only at the leaf."""
    skill = _make_skill(tmp_path, "rules")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "errata.md").write_text("OUTSIDE-SECRET", encoding="utf-8")
    (skill / "resources").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references(
            ("rules/resources/errata.md",), budget=_budget()
        )


def test_an_in_skill_symlink_is_refused(tmp_path):
    """A link that stays inside is refused too: it is the component a swap needs."""
    skill = _make_skill(tmp_path, "rules")
    real = _make_reference(skill, "resources/errata.md", "INSIDE")
    (skill / "alias.md").symlink_to(real)

    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references(("rules/alias.md",), budget=_budget())


def test_a_refusal_does_not_disclose_the_target(tmp_path):
    _make_skill(tmp_path, "rules")
    (tmp_path / "present.md").write_text("x", encoding="utf-8")

    def message(reference: str) -> str:
        with pytest.raises(SkillReferenceError) as exc:
            _resolver(tmp_path).load_references(
                (f"rules/{reference}",), budget=_budget()
            )
        return str(exc.value).replace(reference, "<ref>")

    # An existing out-of-bounds target and an absent one refuse identically, so
    # the error cannot be used to probe the filesystem.
    assert message("../present.md") == message("../absent.md")


def test_an_unknown_skill_in_a_reference_is_refused(tmp_path):
    _make_skill(tmp_path, "rules")
    with pytest.raises(UnknownSkillError) as exc:
        _resolver(tmp_path).load_references(("nope/a.md",), budget=_budget())
    assert "nope" in str(exc.value)


@pytest.mark.parametrize("raw", ["rules", "", "   ", "/", "rules/", "/a.md"])
def test_a_malformed_selection_is_refused(tmp_path, raw):
    _make_skill(tmp_path, "rules")
    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references((raw,), budget=_budget())


@pytest.mark.parametrize(
    "reference",
    [
        # The standard library raises ValueError, not OSError, for an embedded
        # null byte; letting it escape would turn a hostile string into a 500
        # carrying the C-level message instead of this module's one refusal.
        "a\x00b.md",
        # Names the OS itself rejects: over-long, and an unpaired surrogate.
        "a" * 5_000 + ".md",
        "\udcff.md",
    ],
    ids=["null-byte", "over-long", "surrogate"],
)
def test_a_reference_the_os_rejects_is_refused_not_raised(tmp_path, reference):
    _make_skill(tmp_path, "rules")
    with pytest.raises(SkillReferenceError):
        _resolver(tmp_path).load_references((f"rules/{reference}",), budget=_budget())


# --------------------------------------------------------------------------
# Bounds: derived from the context window, not from a count (DRA-54)
# --------------------------------------------------------------------------


def test_the_budget_is_the_window_less_every_configured_reserve():
    """Pinned as LITERALS, so a silently moved constant is a failing test.

    Deliberately NOT asserted against the module's own constants: that form
    still passes when ``PROMPT_FRAME_CHARS`` goes from 12,000 to 120,000 and
    halves the budget, which is exactly the class of change worth catching for
    the three numbers the design admits are projections rather than ceilings.

    Token figures throughout are PROJECTIONS at ~4 chars/token, never measured:
    no judge call is possible without ``EVAL_JUDGE_OPENROUTER_API_KEY``.
    """
    budget = reference_budget(_settings())

    assert budget.window_tokens == 128_000
    assert budget.window_chars == 512_000  # 128,000 tokens x 4 chars
    assert budget.completion_chars == 4_096  # EVAL_JUDGE_MAX_TOKENS x 4
    # A move prompt is the worst of the three scopes at the defaults: two states
    # and 200 neighbours beat a round's one state, 100 moves and 100 verdicts.
    assert budget.binding_scope == "move"
    assert budget.state_chars == 40_000  # prior + resulting, 20,000 each
    assert budget.move_context_chars == 160_000  # 200 neighbours x (400 + 400)
    assert budget.child_context_chars == 0  # a move prompt has no roll-up context
    assert budget.frame_chars == 12_000
    assert budget.chars == 512_000 - 4_096 - 40_000 - 160_000 - 12_000  # 295,904
    # The old fixed bound was 60,000 chars -- 12% of the window.
    assert budget.chars > 4 * 60_000


def test_the_reserve_is_the_worst_scope_not_the_sum_of_all_three():
    """Summing the scopes would reserve for a prompt that cannot exist.

    A move prompt carries neighbours and two states but no roll-up context; a
    round prompt carries a move list, ONE state and its moves' verdicts. Adding
    both reserves would refuse selections that fit every prompt the service can
    actually build.
    """
    # Shrink the move window so the ROUND prompt becomes the worst case.
    budget = reference_budget(
        _settings(eval_judge_move_context_before=1, eval_judge_move_context_after=1)
    )
    assert budget.binding_scope == "round"
    assert budget.state_chars == 20_000  # one closing state, not two
    assert budget.move_context_chars == 100 * (400 + 400)
    assert budget.child_context_chars == 100 * (600 + 200)
    # And it is strictly smaller than the move scope it displaced, so the budget
    # went UP rather than accumulating both.
    assert budget.chars > reference_budget(_settings()).chars


def test_switching_a_per_item_clip_off_does_not_raise_the_budget():
    """``0`` means "do not clip" in the prompt builder, so reserving 0 for it
    would move the reserve the wrong way: less bounded text, more budget."""
    clipped = reference_budget(_settings())
    unclipped = reference_budget(_settings(eval_judge_move_context_reasoning_chars=0))
    assert unclipped.chars < clipped.chars
    assert unclipped.move_context_chars == 200 * (UNCLIPPED_TEXT_PROJECTION_CHARS + 400)


def test_the_budget_moves_with_the_context_window():
    small = reference_budget(_settings(eval_judge_context_window_tokens=32_000))
    large = reference_budget(_settings(eval_judge_context_window_tokens=1_000_000))
    assert small.chars < reference_budget(_settings()).chars < large.chars
    # A window too small to hold the fixed prompt floors at zero rather than
    # going negative and reading as "unbounded".
    assert reference_budget(_settings(eval_judge_context_window_tokens=1)).chars == 0


def test_a_selection_refused_by_a_small_window_is_accepted_by_a_large_one(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "big.md", "B" * 200_000)
    resolver = _resolver(tmp_path)
    requested = JudgeConfig(skill_references=["rules/big.md"])

    with pytest.raises(SkillReferenceBudgetError):
        resolve_judge_config(
            _settings(eval_judge_context_window_tokens=64_000), requested, resolver
        )
    resolved = resolve_judge_config(
        _settings(eval_judge_context_window_tokens=256_000), requested, resolver
    )
    assert resolved.skill_references == ("rules/big.md",)


def test_the_operator_cap_lowers_the_budget_but_cannot_raise_it():
    derived = reference_budget(_settings()).chars
    lowered = reference_budget(_settings(eval_judge_max_skill_reference_chars=1_000))
    assert lowered.chars == 1_000
    assert lowered.capped_by_operator
    # Above the derived budget it buys nothing: the window is not negotiable by a
    # character setting, only by EVAL_JUDGE_CONTEXT_WINDOW_TOKENS.
    raised = reference_budget(
        _settings(eval_judge_max_skill_reference_chars=derived * 10)
    )
    assert raised.chars == derived
    assert not raised.capped_by_operator


def test_selected_skills_and_a_prompt_override_are_charged_to_the_budget(tmp_path):
    """They share the prompt with the references, so they shrink what fits."""
    bare = reference_budget(_settings())
    with_skill = reference_budget(_settings(), skill_chars=90_000, skill_count=5)
    with_override = reference_budget(_settings(), prompt_override_chars=50_000)

    assert with_skill.chars == bare.chars - 90_000
    assert with_override.chars == bare.chars - 50_000


def test_a_selection_that_fits_alone_can_be_refused_alongside_its_skills(tmp_path):
    skill = _make_skill(tmp_path, "rules", "S" * 300_000)
    _make_reference(skill, "big.md", "B" * 200_000)
    resolver = _resolver(tmp_path)

    alone = resolve_judge_config(
        _settings(), JudgeConfig(skill_references=["rules/big.md"]), resolver
    )
    assert alone.skill_references == ("rules/big.md",)

    with pytest.raises(SkillReferenceBudgetError) as exc:
        resolve_judge_config(
            _settings(),
            JudgeConfig(skills=["rules"], skill_references=["rules/big.md"]),
            resolver,
        )
    assert "selected SKILL.md file(s)" in str(exc.value)


def test_the_refusal_states_the_arithmetic_the_operator_can_act_on(tmp_path):
    """The dashboard cannot see reference SIZES, so the 400 is the only place
    a user learns why "select all" did not fit."""
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "big.md", "B" * 400_000)

    with pytest.raises(SkillReferenceBudgetError) as exc:
        resolve_judge_config(
            _settings(),
            JudgeConfig(skill_references=["rules/big.md"]),
            _resolver(tmp_path),
        )
    detail = str(exc.value)
    budget = reference_budget(_settings())
    assert "400000" in detail  # the measured total
    assert str(budget.chars) in detail  # the budget
    assert str(400_000 - budget.chars) in detail  # the overage
    assert "A 128000-token context window" in detail  # where the budget came from
    assert "worst case is the move prompt" in detail  # which scope was reserved
    assert "never truncated" in detail
    for lever in (
        "EVAL_JUDGE_CONTEXT_WINDOW_TOKENS",
        "EVAL_JUDGE_MOVE_CONTEXT_BEFORE",
        "EVAL_JUDGE_MAX_STATE_CHARS",
    ):
        assert lever in detail


def test_an_operator_capped_refusal_names_the_cap_not_the_window(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "big.md", "B" * 5_000)

    with pytest.raises(SkillReferenceBudgetError) as exc:
        resolve_judge_config(
            _settings(eval_judge_max_skill_reference_chars=100),
            JudgeConfig(skill_references=["rules/big.md"]),
            _resolver(tmp_path),
        )
    detail = str(exc.value)
    assert "EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS then lowers that to 100" in detail
    # ...and still says what the window WOULD have allowed, so the operator can
    # tell their own cap from physics.
    assert str(reference_budget(_settings()).chars) in detail
    # The spec's SHALL is unconditional: the reserve terms are present whether or
    # not an operator cap is what bit, because they name the settings to change.
    assert "for the completion" in detail
    assert "for roll-up context" in detail
    assert "EVAL_JUDGE_MOVE_CONTEXT_BEFORE" in detail


def test_more_than_eight_references_are_accepted_by_the_schema():
    """The count ceiling stops being a selection policy (DRA-54).

    Fails before the change with a Pydantic 422 at the ninth entry.
    """
    JudgeConfig(skill_references=[f"rules/r{i}.md" for i in range(50)])
    # The remaining ceiling is a request-BODY guard, not a selection bound.
    with pytest.raises(ValidationError):
        JudgeConfig(skill_references=[f"rules/r{i}.md" for i in range(1_001)])


def test_an_operator_cap_cannot_rescue_a_window_too_small_to_hold_the_prompt():
    """``min(derived, cap)`` with ``derived == 0``: the cap must not resurrect a
    budget the window cannot fund."""
    budget = reference_budget(
        _settings(
            eval_judge_context_window_tokens=1,
            eval_judge_max_skill_reference_chars=50_000,
        )
    )
    assert budget.derived_chars == 0
    assert budget.chars == 0
    # The cap is not what bit -- the window is -- so the refusal says so.
    assert not budget.capped_by_operator


def test_an_operator_cap_and_selected_skills_compose():
    capped = reference_budget(
        _settings(eval_judge_max_skill_reference_chars=100_000),
        skill_chars=90_000,
        skill_count=5,
    )
    # The skills come off the DERIVED budget; the cap then lowers what is left.
    assert capped.derived_chars == reference_budget(_settings()).chars - 90_000
    assert capped.chars == 100_000
    assert capped.capped_by_operator


def test_a_context_window_of_zero_is_refused():
    with pytest.raises(ValidationError):
        Settings(eval_judge_model="x", eval_judge_context_window_tokens=0)


def test_an_over_budget_selection_is_refused_not_truncated(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "big.md", "B" * 5_000)
    _make_reference(skill, "bigger.md", "C" * 5_000)

    with pytest.raises(SkillReferenceBudgetError) as exc:
        _resolver(tmp_path).load_references(
            ("rules/big.md", "rules/bigger.md"), budget=_budget(6_000)
        )
    detail = str(exc.value)
    assert "6000" in detail
    assert "10000" in detail


def test_a_within_budget_selection_is_delivered_in_full(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    body = "B" * 5_000
    _make_reference(skill, "big.md", body)
    loaded = _resolver(tmp_path).load_references(
        ("rules/big.md",), budget=_budget(6_000)
    )
    assert loaded[0].content == body


def test_the_budget_rejects_the_request_before_any_target(tmp_path):
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "big.md", "B" * 5_000)
    settings = _settings(eval_judge_max_skill_reference_chars=100)
    requested = JudgeConfig(skill_references=["rules/big.md"])
    with pytest.raises(SkillReferenceBudgetError):
        resolve_judge_config(settings, requested, _resolver(tmp_path))


def test_the_default_budget_admits_the_whole_shipped_rules_corpus():
    """DRA-54's headline case, against the REAL ``skills/`` directory.

    Fails before DRA-54 twice over: the 21-file selection is refused by the
    schema at reference nine, and its 256,568 characters are refused by the old
    60,000-character budget. Reads the shipped corpus rather than a fixture,
    because the claim being made is about that corpus.
    """
    rules = _shipped_skill("marvel-champions-rules-reference")
    references = sorted(
        p.relative_to(rules).as_posix()
        for p in rules.rglob("*.md")
        if p.name != "SKILL.md"
    )
    assert len(references) > 8, "the point of the test is a selection over eight"

    settings = _settings()
    resolver = SkillResolver((rules.parent,))
    resolved = resolve_judge_config(
        settings,
        JudgeConfig(
            skills=["marvel-champions-rules-reference"],
            skill_references=[
                f"marvel-champions-rules-reference/{name}" for name in references
            ],
        ),
        resolver,
    )
    assert len(resolved.skill_references) == len(references), (
        "the shipped rules corpus no longer fits the derived budget -- the corpus "
        "grew or a reserve term did, not necessarily a bug in reference_budget"
    )


# --------------------------------------------------------------------------
# Nothing that existed before this change moves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("override", [None, "OVERRIDE"], ids=["rubric", "override"])
@pytest.mark.parametrize("skill_references", [None, []], ids=["omitted", "empty"])
def test_a_reference_free_system_prompt_matches_the_pre_change_literal(
    override, skill_references
):
    """The system prompt with no references, pinned as a LITERAL.

    Deliberately not `build(...) == build(..., skill_references=[])`: both of
    those go down the same branch of the same implementation, so that comparison
    can only fail if someone writes a distinct None-vs-empty path, and it would
    happily pass through a change to the heading, the blank lines or the trailing
    newline. This spells the bytes out instead, so DRA-30's "a chat projection
    must not move" guarantee has something that actually breaks when it moves.
    """
    body = "RULESBODY-XYZ"
    messages = build_move_messages(
        _move(),
        prompt_override=override,
        skills=[("rules", body)],
        **({} if skill_references is None else {"skill_references": skill_references}),
    )
    assert messages[0]["content"] == (
        (override or RUBRIC) + "\n\n# Rules reference skills\n"
        "\n## Skill: rules\n\n" + body + "\n"
    )


@pytest.mark.parametrize("override", [None, "OVERRIDE"], ids=["rubric", "override"])
def test_no_skills_and_no_references_is_the_bare_base(override):
    messages = build_move_messages(_move(), prompt_override=override)
    assert messages[0]["content"] == (override or RUBRIC)


def test_a_reference_free_config_keeps_its_prior_digest():
    """Pinned literal: a moved digest silently un-dedupes every stored verdict."""
    config = ResolvedJudgeConfig(
        model="m",
        provider="p",
        reasoning=ResolvedReasoning(enabled=True, effort="high", max_tokens=10),
        prompt_override="po",
        skills=("a", "b"),
    )
    assert "skill_references" not in config.to_json()
    # The digest as it was computed before reference selection existed.
    legacy = {
        "model": "m",
        "provider": "p",
        "reasoning": {"enabled": True, "effort": "high", "max_tokens": 10},
        "prompt_override": "po",
        "skills": ["a", "b"],
    }
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    assert judge_config_digest(config) == expected


def test_a_reference_selection_changes_the_digest_but_its_order_does_not():
    def config(**kw) -> ResolvedJudgeConfig:
        return ResolvedJudgeConfig(
            model="m",
            provider="p",
            reasoning=ResolvedReasoning(enabled=False, effort="medium"),
            prompt_override=None,
            skills=("rules",),
            **kw,
        )

    plain = config()
    selected = config(skill_references=("rules/a.md", "rules/b.md"))
    reordered = config(skill_references=("rules/b.md", "rules/a.md"))

    assert judge_config_digest(selected) != judge_config_digest(plain)
    assert judge_config_digest(selected) == judge_config_digest(reordered)


def test_resolved_config_roundtrips_references():
    config = ResolvedJudgeConfig(
        model="m",
        provider="p",
        reasoning=ResolvedReasoning(enabled=False, effort="medium"),
        prompt_override=None,
        skills=("rules",),
        skill_references=("rules/a.md",),
    )
    assert ResolvedJudgeConfig.from_json(config.to_json()) == config
    # A row written before this change reads back with an empty selection.
    legacy = {"model": "m", "provider": "p", "reasoning": {}, "skills": []}
    assert ResolvedJudgeConfig.from_json(legacy).skill_references == ()


def test_a_selection_is_stored_in_its_canonical_form(tmp_path):
    """Whitespace variants must not become two configs of the same evaluation.

    Parsing strips outer whitespace, so these read the same file and build a
    byte-identical prompt. Storing the caller's string verbatim would give them
    two digests, two idempotency keys, and a duplicate verdict for one grading.
    """
    skill = _make_skill(tmp_path, "rules")
    _make_reference(skill, "errata.md", "E")
    resolver = _resolver(tmp_path)

    plain = resolve_judge_config(
        _settings(), JudgeConfig(skill_references=["rules/errata.md"]), resolver
    )
    padded = resolve_judge_config(
        _settings(), JudgeConfig(skill_references=["  rules/errata.md  "]), resolver
    )
    assert plain.skill_references == ("rules/errata.md",)
    assert padded.skill_references == plain.skill_references
    assert judge_config_digest(padded) == judge_config_digest(plain)


def test_a_negative_reference_budget_is_refused():
    """``0`` means "no cap beyond the window"; a negative value must not, silently."""
    with pytest.raises(ValidationError):
        Settings(eval_judge_model="x", eval_judge_max_skill_reference_chars=-1)
    # Zero is the default and the documented way to say "the window is the bound".
    assert (
        Settings(
            eval_judge_model="x", eval_judge_max_skill_reference_chars=0
        ).eval_judge_max_skill_reference_chars
        == 0
    )

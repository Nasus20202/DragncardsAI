from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval_service.config import Settings, provider_from_model
from eval_service.judge.reference_budget import ReferenceBudget, reference_budget
from eval_service.judge.skill_resources import (
    SKILL_FILE,
    LoadedReference,
    SkillReferenceBudgetError,
    SkillReferenceError,
    load_reference_content,
    parse_reference_selection,
)
from eval_service.schemas.api import JudgeConfig

# Re-exported: it lives next to ``Settings`` (which needs it for the readiness
# provider check) but is part of this module's judge-config surface.
__all__ = [
    "LoadedReference",
    "ReferenceBudget",
    "ResolvedJudgeConfig",
    "ResolvedReasoning",
    "SkillDefinition",
    "SkillReferenceBudgetError",
    "SkillReferenceError",
    "SkillResolver",
    "UnknownSkillError",
    "provider_from_model",
    "resolve_judge_config",
]


class UnknownSkillError(Exception):
    """Raised when a requested skill name cannot be resolved (maps to 400)."""


@dataclass(frozen=True)
class ResolvedReasoning:
    enabled: bool
    effort: str
    max_tokens: int | None = None

    def to_gateway_options(self) -> dict[str, Any]:
        """Map to the Bifrost ``gateway_options`` shape, mirroring the
        agent-orchestrator's ``applyReasoningToGatewayOptions``: when disabled,
        no ``reasoning`` key is sent; when enabled, ``{effort[, max_tokens]}``.
        """
        if not self.enabled:
            return {}
        reasoning: dict[str, Any] = {"effort": self.effort}
        if self.max_tokens is not None:
            reasoning["max_tokens"] = self.max_tokens
        return {"reasoning": reasoning}


@dataclass(frozen=True)
class ResolvedJudgeConfig:
    """The effective judge config for one evaluation, after merging a request's
    ``judge`` overrides over the server (env) defaults. Persisted on the
    request/target rows so the async worker and the SSE stream use it."""

    model: str
    provider: str
    reasoning: ResolvedReasoning
    prompt_override: str | None
    # Selected skill names (resolved separately to markdown content).
    skills: tuple[str, ...] = ()
    # Selected ``<skill-name>/<path>.md`` reference files, resolved separately
    # to markdown content alongside the skills.
    skill_references: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The persisted/hashed form of this config.

        ``skill_references`` is OMITTED when empty, and that is load-bearing
        rather than tidiness: this dict is what ``judge_config_digest`` hashes
        into every verdict's idempotency key. Emitting an empty list
        unconditionally would change the digest of every judge config that has
        ever run, so re-evaluating an already-graded target would record a second
        verdict instead of deduplicating against the first.
        """
        data: dict[str, Any] = {
            "model": self.model,
            "provider": self.provider,
            "reasoning": {
                "enabled": self.reasoning.enabled,
                "effort": self.reasoning.effort,
                "max_tokens": self.reasoning.max_tokens,
            },
            "prompt_override": self.prompt_override,
            "skills": list(self.skills),
        }
        if self.skill_references:
            data["skill_references"] = list(self.skill_references)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "ResolvedJudgeConfig | None":
        if not data:
            return None
        reasoning = data.get("reasoning") or {}
        return cls(
            model=str(data.get("model", "")),
            provider=str(data.get("provider", "")),
            reasoning=ResolvedReasoning(
                enabled=bool(reasoning.get("enabled", False)),
                effort=str(reasoning.get("effort", "medium")),
                max_tokens=reasoning.get("max_tokens"),
            ),
            prompt_override=data.get("prompt_override"),
            skills=tuple(data.get("skills") or ()),
            skill_references=tuple(data.get("skill_references") or ()),
        )


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: Path


class SkillResolver:
    """Resolves skill NAMES to their SKILL.md content under the configured roots.

    Mirrors the agent-orchestrator's skill discovery: each immediate
    subdirectory of a root that contains a ``SKILL.md`` is a skill, named by the
    directory name.
    """

    def __init__(self, roots: tuple[Path, ...]):
        self._roots = roots
        # Cache of (name -> content) per resolved name so a request that expands
        # to many targets re-reads each SKILL.md from disk at most once.
        self._content_cache: dict[str, str] = {}
        # Reference files are deliberately NOT cached. The read is page-cache
        # warm and vanishes next to the LLM round trip it precedes, whereas a
        # cache that never invalidates would pin the largest and most frequently
        # edited files in the corpus -- the errata, the FAQ -- to whatever they
        # said when the process booted, and grade against them for as long as it
        # lives, with no signal that it was doing so.

    def discover(self) -> dict[str, SkillDefinition]:
        discovered: dict[str, SkillDefinition] = {}
        for root in self._roots:
            if not root.exists():
                continue
            for candidate in sorted(root.iterdir()):
                if not candidate.is_dir():
                    continue
                skill_file = candidate / SKILL_FILE
                if skill_file.exists() and candidate.name not in discovered:
                    discovered[candidate.name] = SkillDefinition(
                        name=candidate.name, path=candidate
                    )
        return discovered

    def load_markdown(self, names: tuple[str, ...]) -> list[tuple[str, str]]:
        """Return ``(name, markdown)`` for each requested skill, in order.

        Raises :class:`UnknownSkillError` if any name is not found, so an
        unresolvable selection rejects the whole request before evaluating.
        """
        if not names:
            return []
        available = self.discover()
        unknown = [name for name in names if name not in available]
        if unknown:
            raise UnknownSkillError("unknown skill(s): " + ", ".join(sorted(unknown)))
        out: list[tuple[str, str]] = []
        for name in names:
            content = self._content_cache.get(name)
            if content is None:
                content = (available[name].path / SKILL_FILE).read_text(
                    encoding="utf-8"
                )
                self._content_cache[name] = content
            out.append((name, content))
        return out

    def load_references(
        self, selections: tuple[str, ...], *, budget: ReferenceBudget
    ) -> list[LoadedReference]:
        """Resolve ``<skill>/<path>.md`` selections to their content, in order.

        Raises :class:`UnknownSkillError` when a selection names a skill that
        does not exist, :class:`SkillReferenceError` when a reference cannot be
        resolved inside its skill, and :class:`SkillReferenceBudgetError` when
        the selection's combined size exceeds ``budget``.

        The budget is what is left of the judge model's context window once the
        rest of the prompt is reserved (see
        :mod:`eval_service.judge.reference_budget`); there is no bound on the
        NUMBER of references, because a count measures nothing -- the shipped
        rules skill spans a 20x size range across its files.

        The budget REFUSES rather than clipping. Game state is truncated to fit a
        prompt because a clipped board is still a board; a clipped rules
        reference reads to the judge exactly like a complete one, and grading
        against two thirds of the errata with no way to tell is the defect this
        whole path exists to fix.
        """
        if not selections:
            return []
        available = self.discover()
        # Dedupe by parsed selection: naming the same reference twice would
        # inline two identical blocks and charge the budget twice, so a
        # duplicated errata file alone could trip a limit it fits inside.
        parsed = list(
            dict.fromkeys(parse_reference_selection(raw) for raw in selections)
        )
        unknown = sorted({p.skill for p in parsed if p.skill not in available})
        if unknown:
            raise UnknownSkillError("unknown skill(s): " + ", ".join(unknown))

        out: list[LoadedReference] = []
        total = 0
        for selection in parsed:
            content = load_reference_content(available[selection.skill].path, selection)
            total += len(content)
            if budget.exceeded_by(total):
                raise SkillReferenceBudgetError(budget.refusal(total))
            out.append(
                LoadedReference(
                    skill=selection.skill,
                    reference=selection.reference,
                    content=content,
                )
            )
        return out


def resolve_judge_config(
    settings: Settings,
    requested: JudgeConfig | None,
    skill_resolver: SkillResolver,
) -> ResolvedJudgeConfig:
    """Merge a request's ``judge`` overrides over the env defaults and validate.

    Validates skill names and reference selections eagerly (loads them) so an
    unknown skill, an unresolvable reference, or an over-budget selection is
    raised before any target is enqueued — a bad selection costs the caller a
    400, never a batch of failed targets.
    """
    requested = requested or JudgeConfig()

    model = (requested.model_name or settings.eval_judge_model or "").strip()
    provider = (
        requested.provider_id
        or settings.eval_judge_provider
        or provider_from_model(model)
    ).strip()

    if requested.reasoning is not None:
        reasoning = ResolvedReasoning(
            enabled=requested.reasoning.enabled,
            effort=requested.reasoning.effort,
            max_tokens=requested.reasoning.max_tokens,
        )
    else:
        reasoning = ResolvedReasoning(
            enabled=settings.eval_judge_reasoning_enabled,
            effort=settings.eval_judge_reasoning_effort,
            max_tokens=None,
        )

    prompt_override = requested.prompt_override or None
    skills = tuple(requested.skills or ())
    # Eagerly validate skill names (raises UnknownSkillError on failure). The
    # CONTENT is kept, not discarded: selected SKILL.md files share the prompt
    # with the references, so their size is charged to the reference budget.
    loaded_skills = skill_resolver.load_markdown(skills)

    # Same, for reference selections: resolving them here is what turns a bad
    # path into a 400 instead of a batch of targets that each fail at judge time.
    loaded = skill_resolver.load_references(
        tuple(requested.skill_references or ()),
        budget=reference_budget(
            settings,
            skill_chars=sum(len(content) for _, content in loaded_skills),
            skill_count=len(loaded_skills),
            prompt_override_chars=len(prompt_override or ""),
        ),
    )
    # Keep the CANONICAL selection, not the caller's string. Parsing strips outer
    # whitespace, so ``"rules/a.md"`` and ``"rules/a.md "`` read the same file and
    # build a byte-identical prompt -- but storing them verbatim would give them
    # two different config digests, and so two idempotency keys, and so a
    # duplicate verdict for one evaluation. Canonicalising here keeps the
    # persisted config equal to what the judge was actually shown.
    skill_references = tuple(f"{ref.skill}/{ref.reference}" for ref in loaded)

    return ResolvedJudgeConfig(
        model=model,
        provider=provider,
        reasoning=reasoning,
        prompt_override=prompt_override,
        skills=skills,
        skill_references=skill_references,
    )

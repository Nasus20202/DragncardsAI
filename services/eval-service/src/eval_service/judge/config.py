from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval_service.config import Settings
from eval_service.schemas.api import JudgeConfig


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

    def to_json(self) -> dict[str, Any]:
        return {
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

    def discover(self) -> dict[str, SkillDefinition]:
        discovered: dict[str, SkillDefinition] = {}
        for root in self._roots:
            if not root.exists():
                continue
            for candidate in sorted(root.iterdir()):
                if not candidate.is_dir():
                    continue
                skill_file = candidate / "SKILL.md"
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
                content = (available[name].path / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self._content_cache[name] = content
            out.append((name, content))
        return out


def resolve_judge_config(
    settings: Settings,
    requested: JudgeConfig | None,
    skill_resolver: SkillResolver,
) -> ResolvedJudgeConfig:
    """Merge a request's ``judge`` overrides over the env defaults and validate.

    Validates skill names eagerly (loads them) so an unknown skill raises
    :class:`UnknownSkillError` before any target is enqueued.
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
    # Eagerly validate skill names (raises UnknownSkillError on failure).
    skill_resolver.load_markdown(skills)

    return ResolvedJudgeConfig(
        model=model,
        provider=provider,
        reasoning=reasoning,
        prompt_override=prompt_override,
        skills=skills,
    )


def provider_from_model(model: str) -> str:
    """Best-effort provider id derived from a ``provider/model`` Bifrost id."""
    return model.split("/", 1)[0] if "/" in model else ""

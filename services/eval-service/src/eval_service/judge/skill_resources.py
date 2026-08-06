"""Path-safe access to a skill's reference files.

A skill is a directory holding a ``SKILL.md`` plus, usually, a set of markdown
reference files beside it. ``SKILL.md`` is the summary; the references are the
bulk of the content — ``marvel-champions-rules-reference`` is 21 files and ~12x
the bytes of its own ``SKILL.md``. A judge pointed at that skill without them is
grading against a fraction of the rulebook it was handed.

Reference names arrive from an API caller, so every rule that keeps a caller
inside its own skill directory lives here, in one place, with one refusal:

* the selection must be ``<skill-name>/<relative-path>.md``;
* the path must be relative, canonical, and free of ``.`` / ``..`` components;
* no component may be a symbolic link, so a link cannot be used to step out of
  the skill (or to be swapped for one between the check and the read);
* the resolved file must still be inside the skill directory;
* it must be a regular markdown file, and not the skill's own ``SKILL.md``.

Every refusal raises the SAME message. Which rule a selection broke — and in
particular whether the file it was reaching for exists — is not a caller's to
learn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = [
    "SKILL_FILE",
    "LoadedReference",
    "ReferenceSelection",
    "SkillReferenceBudgetError",
    "SkillReferenceError",
    "load_reference_content",
    "parse_reference_selection",
]

logger = logging.getLogger(__name__)

SKILL_FILE = "SKILL.md"


class SkillReferenceError(Exception):
    """A reference selection that cannot be honoured (maps to 400)."""


class SkillReferenceBudgetError(SkillReferenceError):
    """A selection whose combined reference content exceeds the budget."""


@dataclass(frozen=True)
class ReferenceSelection:
    """One ``<skill-name>/<relative-path>.md`` selection, split into its parts."""

    skill: str
    reference: str

    def __str__(self) -> str:
        return f"{self.skill}/{self.reference}"


@dataclass(frozen=True)
class LoadedReference:
    """One resolved reference file, ready to be placed under its skill."""

    skill: str
    reference: str
    content: str


def parse_reference_selection(raw: str) -> ReferenceSelection:
    """Split ``"<skill>/<reference>"`` into its two coordinates.

    The two coordinates are exactly the arguments the agent-orchestrator's
    ``load_skill_reference`` tool takes, joined, so the same file is named the
    same way whether an agent asks for it or a judge config selects it.

    Splitting on the FIRST separator is what makes a nested reference such as
    ``rules/resources/faq.md`` work: the skill name is one path component and
    everything after it is the reference path.
    """
    text = raw.strip()
    skill, separator, reference = text.partition("/")
    if not separator or not skill.strip() or not reference.strip():
        raise SkillReferenceError(
            f"invalid skill reference {raw!r}: expected '<skill-name>/<path>.md'"
        )
    return ReferenceSelection(skill=skill, reference=reference)


def unresolvable(selection: ReferenceSelection | str) -> SkillReferenceError:
    """The one refusal used for every path rule, so none of them leak."""
    return SkillReferenceError(f"skill reference {str(selection)!r} cannot be resolved")


def load_reference_content(skill_path: Path, selection: ReferenceSelection) -> str:
    """Read one reference file, confined to its own skill directory."""
    try:
        root = skill_path.resolve(strict=True)
    except OSError, ValueError:
        raise unresolvable(selection) from None
    resolved = _resolve_within(root, selection.reference)
    if resolved is None:
        raise unresolvable(selection)
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError, ValueError:
        raise unresolvable(selection) from None


def _refuse(root: Path, reference: str, reason: str) -> None:
    """Log WHY a reference was refused, then refuse.

    The caller gets one message for every rule so the error cannot be used to
    probe the filesystem. The operator gets the specific reason here, because
    "someone is walking paths", "the skills volume is unmounted" and "an operator
    mistyped a filename" all look identical from the outside and need telling
    apart from the inside.
    """
    logger.warning("refusing skill reference %r under %s: %s", reference, root, reason)
    return None


def _resolve_within(root: Path, reference: str) -> Path | None:
    """The file ``reference`` names inside ``root``, or None if any rule refuses.

    ``root`` must already be resolved. Returns None rather than raising so every
    rule reports through the loader's single client-facing refusal, which never
    says which one was broken.
    """
    if not reference or reference != reference.strip():
        return _refuse(root, reference, "empty or untrimmed")
    pure = PurePosixPath(reference)
    # ``pathlib`` already drops "." and "" components, so ".." is the only
    # non-canonical form that survives into ``parts``. A caller that wants
    # ``resources/faq.md`` must say so; ``resources/../resources/faq.md`` names
    # the same file but would leave the audit trail disagreeing with what was
    # read, and the canonical-form check below refuses it either way.
    if pure.is_absolute():
        return _refuse(root, reference, "absolute path")
    if ".." in pure.parts:
        return _refuse(root, reference, "parent-directory traversal")
    if pure.suffix != ".md":
        return _refuse(root, reference, "not a markdown file")
    if pure.name == SKILL_FILE:
        return _refuse(root, reference, f"{SKILL_FILE} is the skill, not a reference")
    # Walk the components so a symlink ANYWHERE on the way down is refused, not
    # only one at the leaf. ``resolve()`` below would already block a link that
    # escapes the skill; refusing links outright also removes the component a
    # check-then-read swap would need, and a rules corpus has no use for one.
    #
    # ``ValueError`` is caught alongside ``OSError`` throughout: the standard
    # library raises it, not ``OSError``, for a path holding an embedded null
    # byte, and letting that escape would turn a hostile string into a 500 with
    # the C-level message attached instead of this module's one refusal.
    walked = root
    for part in pure.parts:
        walked = walked / part
        try:
            if walked.is_symlink():
                return _refuse(root, reference, f"symlinked path component {part!r}")
        except (OSError, ValueError) as exc:
            return _refuse(root, reference, f"unreadable path component: {exc}")
    try:
        resolved = walked.resolve(strict=True)
    except (OSError, ValueError) as exc:
        return _refuse(root, reference, f"does not resolve: {exc}")
    try:
        # Belt and braces: the component walk already refused every symlink, so
        # this cannot differ today. It is the check that would still hold if the
        # walk were ever relaxed, and it costs nothing.
        if resolved.relative_to(root).as_posix() != reference:
            return _refuse(root, reference, "not the file's canonical relative path")
        if not resolved.is_file():
            return _refuse(root, reference, "not a regular file")
    except (OSError, ValueError) as exc:
        return _refuse(root, reference, f"outside the skill or unreadable: {exc}")
    return resolved

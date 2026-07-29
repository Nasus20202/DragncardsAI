"""Generated, human-distinguishable display names for sessions and subagents.

A name produced here has two halves and each does a different job:

* a **codename** — one adjective and one animal, chosen by hashing a stable seed.
  Its only purpose is to be told apart at a glance. Two subagents in the same run
  are "Amber Falcon" and "Silent Otter" rather than two truncations of the same
  boilerplate prompt.
* a **topic** — a few content words lifted out of the prompt. Its purpose is to
  say what the agent was asked to do.

Both halves are pure functions of their inputs, so no name costs a model call and
no name varies between two renders of the same data. Durability comes from
storage, not from recomputation: the name is written once to
``agent_sessions.name`` (and into the ``subagent_started`` event payload) and
every reader afterwards reads that stored string.
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["MAX_GENERATED_NAME_CHARS", "generate_agent_name"]

# The `agent_sessions.name` column holds 255 characters; a name that has to fit a
# sidebar row and a floating list entry should be far shorter than that.
MAX_GENERATED_NAME_CHARS = 96

_MAX_TOPIC_CHARS = 44
_MAX_TOPIC_WORDS = 5
_MIN_WORD_CHARS = 3
_MAX_WORD_CHARS = 14

_SEPARATOR = " · "

_ADJECTIVES = (
    "amber",
    "azure",
    "bold",
    "brave",
    "bright",
    "calm",
    "clever",
    "crimson",
    "dusky",
    "eager",
    "fleet",
    "gentle",
    "golden",
    "hidden",
    "ivory",
    "jade",
    "keen",
    "lively",
    "lucky",
    "noble",
    "quiet",
    "rapid",
    "restless",
    "scarlet",
    "silent",
    "silver",
    "solar",
    "steady",
    "stormy",
    "swift",
    "violet",
    "wily",
)

_NOUNS = (
    "albatross",
    "badger",
    "beacon",
    "bison",
    "cobra",
    "comet",
    "condor",
    "falcon",
    "ferret",
    "gazelle",
    "harrier",
    "heron",
    "ibex",
    "jackal",
    "kestrel",
    "lantern",
    "lynx",
    "magpie",
    "marten",
    "meteor",
    "osprey",
    "otter",
    "panther",
    "quail",
    "raven",
    "sable",
    "sparrow",
    "stoat",
    "tern",
    "vulture",
    "walrus",
    "wolf",
)

# Words that carry no information about what a prompt asked for. The list is
# deliberately blunt: ordinary English function words, plus the instruction
# boilerplate every orchestrator prompt opens with ("you are a subagent … the
# session id is …"), which is exactly the text that made every truncated name
# look identical.
_STOPWORDS = frozenset(
    {
        "about",
        "above",
        "after",
        "again",
        "against",
        "agent",
        "agents",
        "all",
        "already",
        "also",
        "always",
        "and",
        "another",
        "answer",
        "any",
        "anything",
        "are",
        "around",
        "back",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "call",
        "called",
        "calling",
        "calls",
        "can",
        "cannot",
        "child",
        "come",
        "could",
        "detail",
        "details",
        "did",
        "does",
        "doing",
        "done",
        "dont",
        "down",
        "due",
        "each",
        "either",
        "else",
        "enough",
        "etc",
        "even",
        "ever",
        "every",
        "exactly",
        "few",
        "first",
        "following",
        "for",
        "from",
        "full",
        "further",
        "give",
        "given",
        "gives",
        "going",
        "got",
        "had",
        "has",
        "have",
        "having",
        "help",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "however",
        "identifier",
        "into",
        "instead",
        "instructions",
        "its",
        "itself",
        "just",
        "keep",
        "know",
        "last",
        "least",
        "let",
        "like",
        "made",
        "make",
        "many",
        "may",
        "might",
        "more",
        "most",
        "much",
        "must",
        "need",
        "needs",
        "never",
        "next",
        "nor",
        "not",
        "nothing",
        "now",
        "off",
        "once",
        "one",
        "only",
        "onto",
        "other",
        "others",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "per",
        "please",
        "prompt",
        "put",
        "rather",
        "report",
        "request",
        "response",
        "result",
        "results",
        "return",
        "returned",
        "returning",
        "returns",
        "same",
        "say",
        "see",
        "session",
        "sessions",
        "shall",
        "she",
        "should",
        "since",
        "some",
        "something",
        "still",
        "subagent",
        "subagents",
        "such",
        "sure",
        "take",
        "task",
        "tell",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "things",
        "this",
        "those",
        "through",
        "thus",
        "too",
        "tool",
        "tools",
        "under",
        "until",
        "upon",
        "use",
        "used",
        "uses",
        "using",
        "very",
        "via",
        "want",
        "was",
        "well",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "within",
        "without",
        "work",
        "would",
        "you",
        "your",
        "yours",
    }
)

# Atoms are the maximal runs of letters, digits and underscores. Splitting this
# way — rather than on letters alone — is what lets an atom be rejected as a
# whole: `player1Play` and `AbC7dEf9` are single atoms and are discarded, instead
# of shedding their digits and contributing letter fragments to a name.
_ATOM_SPLIT = re.compile(r"[^A-Za-z0-9_]+")


def _codename(seed: str) -> str:
    """Two words chosen by hashing ``seed``. Same seed, same pair, always."""
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    adjective = _ADJECTIVES[value % len(_ADJECTIVES)]
    noun = _NOUNS[(value // len(_ADJECTIVES)) % len(_NOUNS)]
    return f"{adjective.capitalize()} {noun.capitalize()}"


def _is_wordlike(segment: str) -> bool:
    """Whether ``segment`` reads as a word rather than as an opaque string.

    A word is all lower case, all upper case, or capitalised. That excludes the
    mixed-case letter runs that identifiers and credentials are made of — an
    `AbCdEfGh` lifted out of a key would otherwise pass every other test here,
    and a display name is stored and shown to whoever opens the session.
    """
    return segment.isalpha() and (
        segment.islower() or segment.isupper() or segment.istitle()
    )


def _topic(text: str | None) -> str:
    """A short phrase of the content words in ``text``, or "" when there are none.

    Identifiers are dropped whole rather than mined for their letters: an atom
    contributes nothing unless every underscore-separated part of it reads as a
    word. So a UUID, a card id, a group name like `player1Play` and a token
    fragment all drop out, while a tool name like
    `search_cards_marvel_champions` gives up its four words. Words are
    deduplicated so a prompt that repeats its subject does not spend the whole
    budget on one word.
    """
    if not text:
        return ""

    words: list[str] = []
    seen: set[str] = set()
    length = 0
    for atom in _ATOM_SPLIT.split(text):
        segments = [segment for segment in atom.split("_") if segment]
        if not segments or not all(_is_wordlike(segment) for segment in segments):
            continue
        for segment in segments:
            lowered = segment.lower()
            if len(lowered) < _MIN_WORD_CHARS or len(lowered) > _MAX_WORD_CHARS:
                continue
            if lowered in _STOPWORDS or lowered in seen:
                continue
            extra = len(lowered) + (1 if words else 0)
            if length + extra > _MAX_TOPIC_CHARS:
                return " ".join(words)
            seen.add(lowered)
            words.append(lowered)
            length += extra
            if len(words) >= _MAX_TOPIC_WORDS:
                return " ".join(words)

    return " ".join(words)


def generate_agent_name(seed: str, text: str | None = None) -> str:
    """Return a display name for the thing identified by ``seed``.

    ``seed`` should be something already unique and already stored — a session id
    — so that the codename is unique per agent and reproducible from the record.
    ``text`` is the prompt the agent was given, and supplies the topic half.
    """
    codename = _codename(seed)
    topic = _topic(text)
    name = f"{codename}{_SEPARATOR}{topic}" if topic else codename
    return name[:MAX_GENERATED_NAME_CHARS]

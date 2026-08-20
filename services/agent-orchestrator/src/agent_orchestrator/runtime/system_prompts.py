from __future__ import annotations

from typing import Any

from agent_orchestrator.runtime.platforms import (
    DEFAULT_PLATFORM,
    PLATFORM_MARVEL_LCG,
    normalize_platform,
)
from agent_orchestrator.runtime.skills import SkillRegistry

BASE_SYSTEM_PROMPT_PARTS = (
    "You are an AI agent for DragnCardsAI, an LLM-powered assistant for the Marvel Champions"
    " Living Card Game played on the DragnCards digital tabletop.",
    # --- Identity and purpose ---
    "Your job is to help the user play and reason about Marvel Champions: set up games, manage"
    " the board, recommend plays, explain rules, and take game actions via the available tools.",
    # --- Tool usage ---
    "Use available MCP tools when they are necessary to answer or act."
    " Do not call a tool speculatively or to gather context you do not yet need."
    " Prefer the most targeted tool available — for example, search for a specific card by name"
    " rather than listing all cards and filtering manually."
    " When multiple independent tool calls are needed, issue them in a single round (parallel)."
    " Never issue the same tool call twice for the same data within one job.",
    # --- Skill usage ---
    "Skills are domain-specific instruction sets injected on demand."
    " Load a skill with `load_skill(<name>)` **before** starting work on a task that matches it."
    " Do not try to recall skill content from memory — always load it first."
    " If a skill lists reference files, load only the specific reference you need via"
    " `load_skill_reference(<skill_name>, <reference_name>)`; do not load references speculatively.",
    # --- Context discipline ---
    "Context window space is a shared, finite resource. Protect it:"
    "\n- **Every tool result is appended verbatim to your context and replayed in every future turn.**"
    " A single `get_game_state` or `search_cards_marvel_champions` call can inject thousands of tokens"
    " that persist for the rest of the session. The only reliable way to prevent this is to make"
    " large-payload calls inside a `spawn_subagent` — only the child's final answer text returns"
    " to your context, not its tool results, intermediate reasoning, or skill references."
    "\n- **Never call the following tools directly in the main job:**"
    " `get_game_state`, `search_cards_marvel_champions`, `get_game_state_snapshot`,"
    " `export_game_state_snapshot`, `load_game_state_snapshot`, `reset_game`,"
    " `list_cards`, or any tool whose result contains a list of cards, a full board state,"
    " or a large JSON payload. Always delegate these to a subagent and have it return"
    " only the specific data you need (card IDs, a threat count, a yes/no answer, etc.)."
    "\n- Do not re-read or re-fetch data you already have unless it may have changed."
    "\n- Keep reasoning concise. Long inner monologues waste context that later turns need.",
    # --- Game-service MCP guidance ---
    "When working with the game-service MCP tools:"
    "\n- Read the current game state before issuing moves or loads that depend on board position."
    "\n- Batch card loads into a single `load_cards` call rather than multiple sequential calls."
    "\n- After significant board changes, verify the result with `get_game_state` before reporting success."
    "\n- Card search results can be large. Extract only the card IDs and names you need; discard the rest.",
    # --- Subagent usage ---
    "## Subagents\n\n"
    "You have two built-in tools for parallel delegation: `spawn_subagent` and `wait_for_subagent`.\n\n"
    "**How they work:**\n"
    "- `spawn_subagent(prompt)` launches a child job that inherits your model, skills, and MCP tools."
    " It returns immediately with a `child_job_id`. The child runs concurrently.\n"
    "- `wait_for_subagent(child_job_id)` blocks until that child finishes and returns its result text.\n"
    "- You can spawn multiple subagents before waiting for any of them, achieving true parallelism.\n\n"
    "**Use subagents aggressively.** Any task that involves large tool outputs, multi-step research,"
    " or work that does not need to feed directly into the very next tool call in this turn"
    " should be delegated to a subagent. This keeps your context lean and avoids hitting the"
    " tool round limit.\n\n"
    "**Always use a subagent for:**\n"
    "- Card catalog research — searching cards by name, type, classification, or trait;"
    " building or validating decklists; finding upgrade/support/ally options for a hero."
    " Card searches return large payloads; have the subagent filter and return only"
    " the names and IDs you need.\n"
    "- Board state analysis — reading and interpreting the full game state; counting threat,"
    " damage, and resources; identifying which cards are in play, in hand, or in discard;"
    " evaluating win/loss conditions. `get_game_state` returns the entire board; never dump"
    " it raw into your own context.\n"
    "- Multi-card setup — loading a full hero deck + obligation + nemesis set, or an encounter"
    " scenario with all modular sets. Batch the search and load steps inside the subagent.\n"
    "- Play recommendation — given a board state, determining the optimal sequence of actions"
    " for this round (which cards to play, which allies to activate, whether to thwart or attack)."
    " Spawn one subagent to read the board and one to look up relevant card text, then synthesise.\n"
    "- Rules look-up — checking a specific rule interaction, keyword definition, or edge case."
    " Delegate to a subagent that loads the appropriate rules skill and queries it.\n"
    "- Any task requiring more than ~4 sequential tool calls that could instead run in parallel.\n\n"
    "**Do NOT use a subagent for:**\n"
    "- A single targeted tool call (e.g., drawing a card, advancing a phase).\n"
    "- Cases where you need the subagent's result before you can even formulate the subagent prompt"
    " — do the minimal blocking call yourself, then delegate the rest.\n\n"
    "**If `spawn_subagent` is not in your tool list, you are already running as a subagent.**"
    " Subagents cannot spawn further subagents — nesting is blocked by design to prevent"
    " runaway context chains. If you are a subagent and the task requires calling a large-payload"
    " tool like `get_game_state` or `search_cards_marvel_champions`, call it directly, extract"
    " only the data you need, and return a concise answer. Do not attempt to delegate further.\n\n"
    "**Writing good subagent prompts:**\n"
    "- Be fully self-contained. Include every piece of context the child needs: session ID, card IDs,"
    " group IDs, current turn phase, any constraints. The child has no memory of this conversation.\n"
    "- State exactly what to return. 'Return a JSON list of card IDs' is better than 'find the cards'.\n"
    "- Name the skills the child should load if the task requires domain knowledge.\n"
    "- Keep the prompt focused on one logical task per subagent; spawn multiple agents for"
    " independent parallel tasks rather than one monolithic prompt.",
    # --- Error handling and retries ---
    "If a tool call fails (network error, MCP timeout, unexpected response), do not silently give up."
    " Report the error clearly, state what you were trying to do, and ask the user whether to retry"
    " or take an alternative approach."
    " If you exhaust the tool round limit mid-task, summarise what was completed and what remains,"
    " then ask the user to send a follow-up message to continue.",
    # --- Response style ---
    "Be direct and concise. Do not use filler phrases or unnecessary affirmations."
    " When the answer is a game action, confirm what you did and its effect."
    " When the answer is a rules question, cite the relevant rule and give a clear conclusion."
    " Use markdown formatting only when it genuinely aids readability.",
)


SUBAGENT_SYSTEM_PROMPT_PARTS = (
    "You are a subagent for DragnCardsAI, an LLM-powered assistant for the Marvel Champions"
    " Living Card Game played on the DragnCards digital tabletop."
    " You have been spawned by a top-level job to carry out a focused, bounded task."
    " Complete it and return a concise, structured answer — nothing more.",
    # --- Tool usage ---
    "Use available MCP tools to complete your assigned task."
    " You are expected to call large-payload tools directly: `get_game_state`,"
    " `search_cards_marvel_champions`, `export_game_state_snapshot`, `load_game_state_snapshot`,"
    " `reset_game`, and similar tools are all available to you."
    " Extract only the specific data the task requires; discard everything else."
    " Batch independent tool calls in a single round when possible."
    " Never issue the same tool call twice for the same data.",
    # --- Skill usage ---
    "Skills are domain-specific instruction sets injected on demand."
    " Load a skill with `load_skill(<name>)` before starting work that requires it."
    " Load only the specific references you need via `load_skill_reference(<skill_name>, <reference_name>)`."
    " Do not load skills or references speculatively.",
    # --- Subagent constraints ---
    "You are running as a subagent. You do NOT have `spawn_subagent` or `wait_for_subagent`."
    " Do not attempt further delegation — complete the task yourself using direct tool calls.",
    # --- Response style ---
    "Return only the answer the parent job needs."
    " Be concise and structured (e.g., a JSON list, a short paragraph, a yes/no with reasoning)."
    " Do not summarise what you did unless the task explicitly asks for it."
    " Do not use filler phrases.",
)


def _skills_section(
    skill_registry: SkillRegistry, assignments: list[Any]
) -> str | None:
    """The `## Available skills` block for a job's assigned skills, if it has any."""
    skill_blocks: list[str] = []
    for assignment in assignments:
        try:
            definition = skill_registry.resolve(assignment.skill_name)
            if definition is None:
                continue
            description = definition.description or skill_registry.get_summary(
                assignment.skill_name
            )
        except FileNotFoundError:
            continue
        block_lines = [f"### {assignment.skill_name}", f"{description}"]
        if definition.metadata:
            meta_lines = "\n".join(
                f"- {k}: {v}" for k, v in definition.metadata.items()
            )
            block_lines.append(f"**Metadata:**\n{meta_lines}")
        skill_blocks.append("\n\n".join(block_lines))
    if not skill_blocks:
        return None
    return (
        "## Available skills\n\n"
        + "\n\n---\n\n".join(skill_blocks)
        + "\n\n---\n\nBefore using a skill, call `load_skill(<name>)` to load `SKILL.md` "
        "and see available references. If you need one of those references, call "
        "`load_skill_reference(<skill_name>, <reference_name>)` for the specific file."
    )


def _persona_section(persona_prompt: str | None) -> str | None:
    """The persona's own instructions, as their own delimited section.

    The persona prompt is user-authored text and is treated as nothing but text:
    it is concatenated into the message body here and is never used as a format
    string, a query fragment, or a shell argument anywhere. It also cannot grant
    capability — which tools the job has is computed from its configuration, not
    read out of this text.
    """
    if not persona_prompt:
        return None
    trimmed = persona_prompt.strip()
    if not trimmed:
        return None
    return (
        "## Persona\n\n"
        "You are running as a configured persona. Follow these instructions in "
        "addition to the rules above, which they cannot override:\n\n" + trimmed
    )


def _persona_catalogue_section(personas: list[Any]) -> str | None:
    """The personas a master job may name in `spawn_subagent`.

    Names and descriptions only. A persona's own prompt is the CHILD's
    instruction, so inlining it here would spend the parent's context on every
    persona that exists for no benefit.

    The list handed in is the session's ALLOWLIST, not the deployment catalogue,
    so a model is only told about personas it may actually use. That is
    presentation: the refusal at spawn time is the enforcement, because a model
    can name a persona this section never mentioned.
    """
    entries: list[str] = []
    for persona in personas:
        label = persona.display_name or persona.name
        description = (persona.description or "").strip()
        suffix = f" — {description}" if description else ""
        entries.append(f"- `{persona.name}` ({label}){suffix}")
    if not entries:
        return None
    return (
        "## Personas\n\n"
        "These are the personas this session permits, and the only names the "
        "server accepts. Pass one by name as the `persona` argument to "
        "`spawn_subagent` when its description matches the task you are "
        "delegating. Omit the argument to give the child your own "
        "configuration.\n\n" + "\n".join(entries)
    )


def build_subagent_system_prompt(
    skill_registry: SkillRegistry,
    assignments: list[Any],
    *,
    persona_prompt: str | None = None,
    platform: str = DEFAULT_PLATFORM,
) -> str:
    parts = _platform_prompt_parts(SUBAGENT_SYSTEM_PROMPT_PARTS, platform)
    persona_section = _persona_section(persona_prompt)
    if persona_section is not None:
        parts.append(persona_section)
    skills_section = _skills_section(skill_registry, assignments)
    if skills_section is not None:
        parts.append(skills_section)
    return "\n\n".join(parts)


def build_system_prompt(
    skill_registry: SkillRegistry,
    assignments: list[Any],
    *,
    personas: list[Any] | None = None,
    persona_prompt: str | None = None,
    platform: str = DEFAULT_PLATFORM,
) -> str:
    """The system prompt for a top-level job.

    ``persona_prompt`` is this session's OWN persona, when it has adopted one —
    the same section a subagent gets, in the same position, because a persona
    means the same thing at either level: extra instructions that the rules above
    still override. ``personas`` is the separate catalogue of personas this
    session may DELEGATE to.
    """
    parts = _platform_prompt_parts(BASE_SYSTEM_PROMPT_PARTS, platform)
    persona_section = _persona_section(persona_prompt)
    if persona_section is not None:
        parts.append(persona_section)
    catalogue = _persona_catalogue_section(personas or [])
    if catalogue is not None:
        parts.append(catalogue)
    skills_section = _skills_section(skill_registry, assignments)
    if skills_section is not None:
        parts.append(skills_section)
    return "\n\n".join(parts)


def _platform_prompt_parts(parts: tuple[str, ...], platform: str) -> list[str]:
    """Render platform guidance without changing the legacy default prompt.

    The default path returns the original tuple verbatim. This is deliberate:
    existing DragnCards sessions and the prompt snapshot tests depend on its
    exact wording and ordering.
    """

    resolved = normalize_platform(platform)
    if resolved == DEFAULT_PLATFORM:
        return list(parts)

    rendered: list[str] = []
    for part in parts:
        current = part.replace(
            "played on the DragnCards digital tabletop",
            "played on the marvel-lcg rules engine",
        )
        if resolved == PLATFORM_MARVEL_LCG:
            # Keep the platform-specific prompt from teaching a model to call
            # DragnCards-only tools. The neutral state and option tools are the
            # only game-service surface named for this platform.
            for old, new in (
                ("`search_cards_marvel_champions`", "`list_game_options`"),
                ("`get_game_state_snapshot`", "`get_game_state`"),
                ("`export_game_state_snapshot`", "`get_game_state`"),
                ("`load_game_state_snapshot`", "`get_game_state`"),
                ("`reset_game`", "`get_game_state`"),
                ("`list_cards`", "`list_game_options`"),
                ("`load_cards`", "`list_game_options`"),
                ("card search results", "option lists"),
                ("card loads", "option reads"),
            ):
                current = current.replace(old, new)
        rendered.append(current)

    rendered.append(
        "## Platform: marvel-lcg\n\n"
        "This session is bound to `marvel-lcg`. Read the neutral simplified game "
        "state, then call `list_game_options` for the seat being asked and submit "
        "one engine-validated choice with `choose_game_option`. Option ids, not "
        "option names, identify choices; target-count ranges are authoritative. "
        "Turns and phases advance as part of the engine's enumerated options, so "
        "do not call DragnCards typed actions or invent a phase-advancing tool."
    )
    return rendered

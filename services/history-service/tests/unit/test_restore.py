from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from history_service.runtime.restore import RestoreError, RestoreService
from history_service.integrations.game_service import BranchSession
from history_service.schemas.envelope import EventEnvelope


def _env(game_id, actor, offset, *, event_type, payload):
    return EventEnvelope(
        game_id=game_id,
        actor=actor,
        event_type=event_type,
        payload=payload,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:{actor}:{offset}",
        producer_offset=offset,
    )


class FakeGameService:
    def __init__(self):
        self.loaded: list[tuple[str, dict]] = []
        self.replayed: list[tuple[str, dict]] = []
        self.created: list[str] = []
        self.created_ephemeral: list[bool] = []
        self.deleted: list[str] = []
        self.state = {"state": {"mode": "in progress"}}
        self._created_count = 0
        self.replay_error: Exception | None = None
        self.load_error: Exception | None = None

    async def create_session(self, plugin_name, *, ephemeral=False):
        self.created.append(plugin_name)
        self.created_ephemeral.append(ephemeral)
        self._created_count += 1
        return BranchSession(
            session_id=f"branch-session-{self._created_count}",
            room_slug=f"branch-room-{self._created_count}",
        )

    async def delete_session(self, game_id):
        self.deleted.append(game_id)

    async def load_snapshot(self, game_id, snapshot):
        if self.load_error is not None:
            raise self.load_error
        self.loaded.append((game_id, snapshot))
        return {"session_id": game_id}

    async def replay_action(self, game_id, action):
        if self.replay_error is not None:
            raise self.replay_error
        self.replayed.append((game_id, action))
        return {"ok": True}

    async def get_state(self, game_id):
        return self.state

    async def get_snapshot(self, game_id):
        return {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}


class FakeOrchestrator:
    def __init__(self):
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def restore_session(self, *, game_id, conversation_context, mode):
        self.calls.append(
            {"game_id": game_id, "context": conversation_context, "mode": mode}
        )
        if self.error is not None:
            raise self.error
        return {"session_id": "orch-session-1"}


async def _seed_recorded_game(repository):
    # seq 1: game-service state
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            0,
            event_type="state",
            payload={"status": "in progress"},
        )
    )
    # seq 2: agent move with conversation context + action
    await repository.commit_event(
        _env(
            "g1",
            "agent",
            1,
            event_type="move",
            payload={
                "intended_action": "play",
                "conversation_context": {
                    "messages": [{"role": "user", "content": "hi"}]
                },
            },
        )
    )
    # seq 3: game-service mutating action
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            2,
            event_type="action",
            payload={
                "action_path": "move_card",
                "action_args": {"card_id": "c1"},
                "status": "in progress",
            },
        )
    )
    # seq 4: another game-service action
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            3,
            event_type="action",
            payload={
                "action_path": "draw_card",
                "action_args": {},
                "status": "in progress",
            },
        )
    )


@pytest.mark.asyncio
async def test_restore_nearest_snapshot_then_replay(repository):
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=4, mode="new")

    # nearest snapshot at seq 2 loaded; events 3 and 4 replayed forward.
    assert result.snapshot_at_seq == 2
    assert result.replayed_event_seqs == [3, 4]
    assert [a["action_path"] for _, a in game.replayed] == ["move_card", "draw_card"]
    # agent event at/<= seq 4 is seq 2; its context handed to orchestrator.
    # The wrapped {"messages": [...]} payload is normalized to a flat list, which
    # is what the orchestrator restore endpoint expects.
    assert orch.calls[0]["context"] == [{"role": "user", "content": "hi"}]
    assert result.orchestrator_session_id == "orch-session-1"


@pytest.mark.asyncio
async def test_restore_agent_events_not_replayed_as_mutations(repository):
    await _seed_recorded_game(repository)
    # A snapshot is needed so a "new" branch session can learn the plugin_name.
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=4, mode="new")
    # Only game-service mutating events (seq 3, 4) replayed; agent seq 2 excluded.
    assert result.replayed_event_seqs == [3, 4]
    assert all("action_path" in a for _, a in game.replayed)


@pytest.mark.asyncio
async def test_restore_new_sources_plugin_name_from_state_event_without_snapshot(
    repository,
):
    """A short game with NO snapshot can still branch: the plugin slug is sourced
    from the earliest game-state event payload."""
    # seq 1: game-service state carrying the plugin slug (as the emitter records).
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            0,
            event_type="state",
            payload={"status": "in progress", "plugin_name": "marvel-champions"},
        )
    )
    # seq 2: a mutating game-service action to replay forward.
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            1,
            event_type="action",
            payload={
                "action_path": "draw_card",
                "action_args": {},
                "status": "in progress",
            },
        )
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=2, mode="new")

    # No snapshot existed, yet a branch session was created from the slug found
    # on the earliest state event, then the action replayed forward.
    assert result.snapshot_at_seq is None
    assert game.created == ["marvel-champions"]
    assert result.replayed_event_seqs == [2]


@pytest.mark.asyncio
async def test_restore_new_loads_full_state_from_nearest_state_event(repository):
    """The board base is the nearest game-state event's FULL state, so setup
    actions that were never recorded as replayable (e.g. deck loads) are still
    reflected — no empty board."""
    # seq 1: a game-state event carrying the complete board state.
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            0,
            event_type="state",
            payload={
                "status": "in progress",
                "plugin_name": "marvel-champions",
                "state": {"game": {"mode": "in progress", "cardById": {"c1": {}}}},
            },
        )
    )
    # seq 2: a later mutating action after the state base.
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            1,
            event_type="action",
            payload={
                "action_path": "actions",
                "action_args": {"type": "exhaust_card", "instance_id": "c1"},
                "status": "in progress",
                "state": {"game": {"mode": "in progress", "cardById": {"c1": {}}}},
            },
        )
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=1, mode="new", ephemeral=True)

    # The full state from the seq-1 state event was loaded as the base (not an
    # empty replay-from-zero), carrying the cards.
    assert len(game.loaded) == 1
    _, doc = game.loaded[0]
    assert doc["plugin_name"] == "marvel-champions"
    assert doc["game"]["cardById"] == {"c1": {}}
    assert result.snapshot_at_seq == 1
    # Target was the state base itself, so nothing needed replay.
    assert result.replayed_event_seqs == []


@pytest.mark.asyncio
async def test_restore_no_prior_snapshot_replays_from_one(repository):
    await _seed_recorded_game(repository)
    # Snapshot sits AFTER the target so no snapshot precedes the restore point
    # (no load), but the branch session can still learn the plugin_name from it.
    await repository.write_snapshot(
        "g1", 4, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=3, mode="new")
    assert result.snapshot_at_seq is None
    assert game.loaded == []  # no snapshot import
    assert result.replayed_event_seqs == [3]
    # A real branch session was created via game-service create_session.
    assert game.created == ["marvel-champions"]
    assert result.game_session_id == "branch-session-1"


@pytest.mark.asyncio
async def test_restore_new_mode_leaves_original_untouched(repository):
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=3, mode="new")
    assert result.game_session_id != "g1"
    assert result.game_session_id == "branch-session-1"
    assert result.mode == "new"
    # original event log untouched
    assert len(await repository.list_events("g1")) == 4


@pytest.mark.asyncio
async def test_restore_in_place_targets_live_session(repository):
    await _seed_recorded_game(repository)
    # An in-place rewind requires a snapshot at/<= target to establish a clean
    # base; load it, then replay seq 3 forward onto that reset state.
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=3, mode="in_place")
    assert result.game_session_id == "g1"
    assert result.mode == "in_place"
    assert orch.calls[0]["mode"] == "in_place"
    # The clean base was loaded into the live session before forward replay.
    assert game.loaded and game.loaded[0][0] == "g1"
    assert result.snapshot_at_seq == 2
    assert result.replayed_event_seqs == [3]


@pytest.mark.asyncio
async def test_restore_in_place_without_any_base_rejected(repository):
    """No full-state base at/<= target: in-place rewind is rejected.

    Neither a snapshot nor a usable game-state event exists here (these events
    record no ``plugin_name`` and no ``state``), so there is no clean base to
    reset to and forward replay would double-apply onto the un-rewound live
    state. Reject rather than corrupt the live session.
    """
    await _seed_recorded_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=3, mode="in_place")
    # Nothing was mutated on the live session.
    assert game.loaded == [] and game.replayed == [] and orch.calls == []


@pytest.mark.asyncio
async def test_restore_mid_replay_failure_raises_restore_error(repository):
    """A mid-replay failure surfaces as RestoreError, not an unhandled 500."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    game.replay_error = RuntimeError("game-service exploded mid-replay")
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=4, mode="new")


@pytest.mark.asyncio
async def test_restore_new_mode_cleans_up_branch_on_failure(repository):
    """A new-mode restore that fails after creating a room deletes that room."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    game.replay_error = RuntimeError("game-service exploded mid-replay")
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=4, mode="new")
    # The branch room created for the restore was rolled back.
    assert game.created == ["marvel-champions"]
    assert game.deleted == ["branch-session-1"]


@pytest.mark.asyncio
async def test_restore_rejects_out_of_range(repository):
    await _seed_recorded_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=99, mode="new")
    # nothing mutated
    assert game.loaded == [] and game.replayed == [] and orch.calls == []


@pytest.mark.asyncio
async def test_restore_unknown_game_rejected(repository):
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    with pytest.raises(RestoreError):
        await service.restore("nope", target_seq=1, mode="new")


@pytest.mark.asyncio
async def test_restore_skips_evaluator_events_in_replay(repository):
    """``evaluator`` verdict events are advisory and never replayed as mutations.

    The forward-replay path only replays ``game-service`` mutating events, so an
    ``evaluator`` event interleaved on the timeline must not be applied to the
    game session (it is not a game mutation).
    """
    await _seed_recorded_game(repository)
    # Interleave an evaluator verdict event after the move (seq 5).
    await repository.commit_event(
        _env(
            "g1",
            "evaluator",
            5,
            event_type="evaluation",
            payload={
                "scope": "move",
                "target_seq": 2,
                "scores": {
                    "rules_legality": 8,
                    "strategic_quality": 6,
                    "tempo_efficiency": 7,
                    "threat_resource": 7,
                },
                "overall_score": 7,
                "rationale": "ok",
                "flags": [],
                # action_path is deliberately set to prove the actor filter (not
                # the mutating-event filter) is what excludes evaluator events.
                "action_path": "move_card",
            },
        )
    )
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=5, mode="new")
    # Only the game-service mutating events (seq 3, 4) replayed; the evaluator
    # event at seq 5 is excluded even though it carries an action_path.
    assert result.replayed_event_seqs == [3, 4]
    replayed_paths = [a.get("action_path") for _, a in game.replayed]
    assert replayed_paths == ["move_card", "draw_card"]


@pytest.mark.asyncio
async def test_restore_verifies_status_and_flags_divergence(repository):
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    game.state = {"state": {"mode": "loss"}}  # differs from recorded "in progress"
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )
    result = await service.restore("g1", target_seq=4, mode="new")
    assert result.status_verified is False
    assert result.divergence is not None


@pytest.mark.asyncio
async def test_restore_ephemeral_flag_passed_to_branch_creation(repository):
    """``ephemeral=True`` is threaded through to game-service branch creation."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=4, mode="new", ephemeral=True)

    # A real (ephemeral) branch session was created and tagged ephemeral.
    assert game.created == ["marvel-champions"]
    assert game.created_ephemeral == [True]
    assert result.game_session_id == "branch-session-1"
    assert result.mode == "new"
    # A view-only ephemeral reconstruction must NOT create an orchestrator
    # agent session.
    assert orch.calls == []
    assert result.orchestrator_session_id is None


@pytest.mark.asyncio
async def test_restore_non_ephemeral_restores_agent_context(repository):
    """A kept (non-ephemeral) branch still restores the agent conversation."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=4, mode="new")

    assert orch.calls and orch.calls[0]["context"] == [
        {"role": "user", "content": "hi"}
    ]
    assert result.orchestrator_session_id == "orch-session-1"


@pytest.mark.asyncio
async def test_restore_defaults_to_non_ephemeral_branch(repository):
    """Without the flag, a ``mode="new"`` branch is created as kept (non-ephemeral)."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 2, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    await service.restore("g1", target_seq=4, mode="new")

    assert game.created_ephemeral == [False]


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """An httpx error shaped like a real upstream failure response."""
    request = httpx.Request("POST", "http://upstream/whatever")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(f"{status_code}", request=request, response=response)


async def _seed_state_event_game(repository, *, plugin_name="marvel-champions"):
    """A short game whose game-state event carries a full board and the slug."""
    await repository.commit_event(
        _env(
            "g1",
            "game-service",
            0,
            event_type="state",
            payload={
                "status": "in progress",
                "plugin_name": plugin_name,
                "state": {"game": {"mode": "in progress", "cardById": {"c1": {}}}},
            },
        )
    )
    await repository.commit_event(
        _env(
            "g1",
            "agent",
            1,
            event_type="move",
            payload={
                "intended_action": "play",
                "conversation_context": [{"role": "user", "content": "hi"}],
            },
        )
    )


@pytest.mark.asyncio
async def test_in_place_restore_survives_no_active_agent_session(repository):
    """DRA-26: an in-place rewind must NOT fail because the agent session that
    played the game is gone.

    The orchestrator answers 404 when no ACTIVE session is bound to the game,
    which is the normal state for any game being browsed in history. That 404
    used to propagate: the live game was rewound and the caller was then told the
    restore had failed, with a bare "404" naming neither service nor cause.
    """
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    orch.error = _http_error(404)
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=2, mode="in_place")

    # The game-state layer completed against the live session.
    assert result.game_session_id == "g1"
    assert result.mode == "in_place"
    assert game.loaded and game.loaded[0][0] == "g1"
    # ...and the missing agent session is reported, not raised.
    assert result.orchestrator_session_id is None
    assert result.agent_context_restored is False
    assert result.agent_context_note is not None
    assert "no active agent session" in result.agent_context_note.lower()


@pytest.mark.asyncio
async def test_in_place_restore_still_fails_on_a_real_orchestrator_error(repository):
    """Only a 404 is tolerated. A 500 is a genuine fault and must surface."""
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    orch.error = _http_error(500)
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=2, mode="in_place")


@pytest.mark.asyncio
async def test_in_place_restore_uses_a_state_event_base_without_any_snapshot(
    repository,
):
    """DRA-26: in-place no longer requires a periodic snapshot.

    A game-state event embeds a complete board, so it is an equally valid clean
    base. Requiring a snapshot rejected every game shorter than one snapshot
    cadence — which is most games a user browses.
    """
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=1, mode="in_place")

    assert result.game_session_id == "g1"
    assert result.snapshot_at_seq == 1
    # The full recorded board was loaded into the live session as the base.
    assert game.loaded[0][0] == "g1"
    assert game.loaded[0][1]["game"] == {
        "mode": "in progress",
        "cardById": {"c1": {}},
    }


@pytest.mark.asyncio
async def test_in_place_restore_reports_a_deleted_live_session_clearly(repository):
    """A 404 loading the base means the live room is gone; say so actionably."""
    await _seed_state_event_game(repository)
    game = FakeGameService()
    game.load_error = _http_error(404)
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    with pytest.raises(RestoreError) as excinfo:
        await service.restore("g1", target_seq=1, mode="in_place")

    message = str(excinfo.value)
    assert "no longer exists" in message
    assert "branchable" in message
    # Nothing was replayed onto a session that does not exist.
    assert game.replayed == []


@pytest.mark.asyncio
async def test_branch_restore_returns_the_new_room_slug(repository):
    """DRA-26/DRA-28: a branch restore's product is a room, so name it.

    Without the slug on the response the caller has to list every live session
    and search it by id -- an extra round trip and a race with the reaper.
    """
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=1, mode="new")

    assert result.game_session_id == "branch-session-1"
    assert result.room_slug == "branch-room-1"


@pytest.mark.asyncio
async def test_in_place_restore_does_not_carry_a_room_slug(repository):
    """An in-place rewind creates no room, so it reports none."""
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    result = await service.restore("g1", target_seq=1, mode="in_place")

    assert result.room_slug is None


@pytest.mark.asyncio
async def test_replay_range_read_is_filtered_to_game_service_events(repository):
    """DRA-28: the replay range must be narrowed in the database.

    Every game-state payload embeds a whole board, so fetching a range whole and
    skipping non-game-service rows in Python transferred and parsed megabytes to
    discard them. Assert the query itself is filtered.
    """
    await _seed_state_event_game(repository)
    seen: list[str | None] = []
    original = repository.get_events_in_range

    async def spy(game_id, *, low_exclusive, high_inclusive, actor=None):
        seen.append(actor)
        return await original(
            game_id,
            low_exclusive=low_exclusive,
            high_inclusive=high_inclusive,
            actor=actor,
        )

    repository.get_events_in_range = spy  # type: ignore[method-assign]
    service = RestoreService(
        repository=repository,
        game_service=FakeGameService(),
        orchestrator=FakeOrchestrator(),
    )

    await service.restore("g1", target_seq=2, mode="new")

    assert seen == ["game-service"]


@pytest.mark.asyncio
async def test_branch_restore_does_not_swallow_an_orchestrator_404(repository):
    """The 404 tolerance is gated on mode="in_place", and must stay that way.

    Only the orchestrator's in-place branch looks a session up and can legitimately
    answer 404; its "new" branch unconditionally creates one and has no 404 path.
    So a 404 during a branch restore means the endpoint was never reached — a wrong
    base URL, or a route moved by a version skew. Because this is the only call
    history-service makes to agent-orchestrator, swallowing it would turn a broken
    deployment into a reassuring note with no other signal to catch it.
    """
    await _seed_state_event_game(repository)
    game = FakeGameService()
    orch = FakeOrchestrator()
    orch.error = _http_error(404)
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=orch
    )

    with pytest.raises(RestoreError):
        await service.restore("g1", target_seq=2, mode="new")

    # The half-built branch room was rolled back rather than left orphaned.
    assert game.deleted == ["branch-session-1"]


# ---------------------------------------------------------------------------
# Restore into an existing session (DRA-36)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reuse_loads_the_base_into_the_supplied_session(repository):
    """The saving: no room is built, the caller's open room is re-pointed."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    result = await service.restore(
        "g1", target_seq=4, mode="new", ephemeral=True, reuse_session_id="mine"
    )

    assert game.created == []
    assert result.game_session_id == "mine"
    assert [session for session, _ in game.loaded] == ["mine"]
    assert result.replayed_event_seqs == [4]
    # No room was created, so none is reported; the caller already knows the room
    # it handed over.
    assert result.room_slug is None


@pytest.mark.asyncio
async def test_reuse_ends_in_the_same_state_as_a_fresh_session(repository):
    """A reused session must carry nothing over from the moment it last held.

    Both paths reach the target the same way: load the same full-state base, then
    replay the same forward range. That is what makes the reuse safe, so it is
    asserted directly rather than inferred.
    """
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )

    fresh_game = FakeGameService()
    fresh = await RestoreService(
        repository=repository, game_service=fresh_game, orchestrator=FakeOrchestrator()
    ).restore("g1", target_seq=4, mode="new", ephemeral=True)

    reused_game = FakeGameService()
    # The session already holds an earlier moment of this game.
    await RestoreService(
        repository=repository, game_service=reused_game, orchestrator=FakeOrchestrator()
    ).restore("g1", target_seq=3, mode="new", ephemeral=True, reuse_session_id="mine")
    reused_game.loaded.clear()
    reused_game.replayed.clear()
    reused = await RestoreService(
        repository=repository, game_service=reused_game, orchestrator=FakeOrchestrator()
    ).restore("g1", target_seq=4, mode="new", ephemeral=True, reuse_session_id="mine")

    assert reused.snapshot_at_seq == fresh.snapshot_at_seq
    assert reused.replayed_event_seqs == fresh.replayed_event_seqs
    # Same base document, same forward actions — differing only in which session
    # they were applied to.
    assert [doc for _, doc in reused_game.loaded] == [
        doc for _, doc in fresh_game.loaded
    ]
    assert [action for _, action in reused_game.replayed] == [
        action for _, action in fresh_game.replayed
    ]


@pytest.mark.asyncio
async def test_reuse_is_declined_when_no_full_state_base_exists(repository):
    """Without a base, replay starts from seq 1 onto whatever is already there.

    In a fresh session that is a new game; in a reused one it is the previous
    view. The gate excludes the path rather than reasoning about which replays
    happen to be total.
    """
    await _seed_recorded_game(repository)
    # The only snapshot sits AFTER the target, so no base precedes it — but the
    # plugin name is still discoverable, so a fresh branch can be created.
    await repository.write_snapshot(
        "g1", 4, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    result = await service.restore(
        "g1", target_seq=3, mode="new", ephemeral=True, reuse_session_id="mine"
    )

    assert game.created == ["marvel-champions"]
    assert result.game_session_id == "branch-session-1"
    # The supplied session was neither loaded into nor deleted.
    assert [session for session, _ in game.loaded] == []
    assert "mine" not in game.deleted


@pytest.mark.asyncio
async def test_reuse_is_ignored_for_an_in_place_restore(repository):
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    result = await service.restore(
        "g1", target_seq=4, mode="in_place", reuse_session_id="mine"
    )

    assert result.game_session_id == "g1"
    assert [session for session, _ in game.loaded] == ["g1"]


@pytest.mark.asyncio
async def test_a_failed_reuse_restore_does_not_delete_the_supplied_session(repository):
    """The caller owns a supplied session, so rollback must not reclaim it."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    game.replay_error = RuntimeError("replay blew up")
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    with pytest.raises(RestoreError):
        await service.restore(
            "g1", target_seq=4, mode="new", ephemeral=True, reuse_session_id="mine"
        )

    assert game.deleted == []


@pytest.mark.asyncio
async def test_a_plugin_mismatch_on_the_supplied_session_is_a_client_error(repository):
    """game-service rejects a snapshot whose plugin differs; report it as 4xx."""
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    game.load_error = _http_error(400)
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    with pytest.raises(RestoreError):
        await service.restore(
            "g1", target_seq=4, mode="new", ephemeral=True, reuse_session_id="mine"
        )

    assert game.deleted == []


@pytest.mark.asyncio
async def test_reuse_is_declined_for_a_kept_branch_restore(repository):
    """Reuse is for throwaway reconstructions, not for a branch meant to be kept.

    It overwrites a session the caller names rather than one the restore created,
    so without this gate the field would be a way to replace an unrelated live
    session's board with a different game's.
    """
    await _seed_recorded_game(repository)
    await repository.write_snapshot(
        "g1", 3, {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}
    )
    game = FakeGameService()
    service = RestoreService(
        repository=repository, game_service=game, orchestrator=FakeOrchestrator()
    )

    result = await service.restore(
        "g1", target_seq=4, mode="new", ephemeral=False, reuse_session_id="mine"
    )

    assert game.created == ["marvel-champions"]
    assert result.game_session_id == "branch-session-1"
    assert [session for session, _ in game.loaded] == ["branch-session-1"]
    assert "mine" not in game.deleted

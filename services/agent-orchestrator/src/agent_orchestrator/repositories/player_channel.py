"""Persistence for the two out-of-band channels a player seat has.

Both are keyed on the *orchestrating* session, because a seat's own session is a
separate ``agent_sessions`` row: the orchestrating session is the only identifier
the sender and the recipient of a message share, and the only one that scopes a
finding to one game.

Two of the writes here are conditional, and the reason is the same in both cases
as it is for ``set_player_agent_session``: the transition must happen exactly
once even when two callers attempt it concurrently on two replicas. Each is an
``UPDATE ... WHERE <the state it is leaving>``, and the rows it reports are the
decision — delivering a message twice would replay it into a seat's context, and
resolving a finding twice would record a second resolution of something already
closed.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import (
    AgentSession,
    PlayerIllegalAction,
    PlayerMessage,
)

ILLEGAL_ACTION_STATUS_OPEN = "open"
ILLEGAL_ACTION_STATUS_RESOLVED = "resolved"


class PlayerChannelRepositoryMixin:
    """Player-to-player messages, and illegal-action findings against a seat."""

    async def send_player_message(
        self,
        session_id: str,
        *,
        sender_player_id: str,
        recipient_player_id: str,
        body: str,
    ) -> PlayerMessage | None:
        """Store one message from one seat to another.

        ``session_id`` is the orchestrating session both seats belong to. Returns
        ``None`` when that session does not exist, so the caller can refuse rather
        than write a row nothing will ever read. The sender is supplied by the
        server from the caller's seat identity and is never taken from the
        message body.
        """
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            item = PlayerMessage(
                session_id=session_id,
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
                body=body,
            )
            session.add(item)
            await session.flush()
            message_id = item.id
        return await self.get_player_message(message_id)

    async def get_player_message(self, message_id: str) -> PlayerMessage | None:
        async with self._session_factory() as session:
            return await session.get(PlayerMessage, message_id)

    async def list_player_messages(self, session_id: str) -> list[PlayerMessage]:
        """Every message sent at one table, oldest first.

        Reads the whole channel regardless of delivery state, which is what a
        test or an operator inspecting a game wants. Delivery uses
        :meth:`list_undelivered_player_messages` instead.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerMessage)
                .where(PlayerMessage.session_id == session_id)
                .order_by(PlayerMessage.created_at, PlayerMessage.id)
            )
            return list(result.scalars().unique())

    async def list_undelivered_player_messages(
        self, session_id: str, recipient_player_id: str
    ) -> list[PlayerMessage]:
        """Messages waiting for one seat, oldest first.

        Ordered by creation so a seat reads a conversation in the order it
        happened. The id is a tiebreaker because two messages written in the same
        instant would otherwise come back in an arbitrary order.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerMessage)
                .where(
                    PlayerMessage.session_id == session_id,
                    PlayerMessage.recipient_player_id == recipient_player_id,
                    PlayerMessage.delivered_at.is_(None),
                )
                .order_by(PlayerMessage.created_at, PlayerMessage.id)
            )
            return list(result.scalars().unique())

    async def mark_player_messages_delivered(
        self, message_ids: Sequence[str]
    ) -> list[str]:
        """Mark messages delivered, returning only the ones this call claimed.

        Conditional on ``delivered_at IS NULL``, and the ids it returns are the
        ids it actually transitioned. Two concurrent invocations of the same seat
        — a retried job and its replacement, say — therefore cannot both deliver
        one message: the loser is told it claimed nothing and delivers nothing.
        The caller must frame only what it gets back, because anything else is
        already in some other invocation's context.

        Each id is updated on its own rather than in one ``IN`` clause, so the
        result is exact per message instead of per batch. A single statement
        reports only how many rows it changed, which cannot distinguish "all of
        them" from "all but the one a concurrent caller had already taken" — and
        assuming the former is how the same message ends up in two contexts.
        """
        ids = list(dict.fromkeys(message_ids))
        claimed: list[str] = []
        if not ids:
            return claimed
        async with self._session_factory() as session, session.begin():
            for message_id in ids:
                result = await session.execute(
                    update(PlayerMessage)
                    .where(
                        PlayerMessage.id == message_id,
                        PlayerMessage.delivered_at.is_(None),
                    )
                    .values(delivered_at=utc_now())
                )
                if result.rowcount:
                    claimed.append(message_id)
        return claimed

    async def open_illegal_action(
        self,
        session_id: str,
        *,
        player_id: str,
        violation: str,
        required_undo: str,
        round_number: int | None = None,
    ) -> PlayerIllegalAction | None:
        """Record that a seat's action broke the rules.

        Returns ``None`` when the orchestrating session does not exist. A finding
        starts ``open`` and stays open until the orchestrating agent resolves it,
        which it may do only after verifying the undo against game state.
        """
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            item = PlayerIllegalAction(
                session_id=session_id,
                player_id=player_id,
                round_number=round_number,
                violation=violation,
                required_undo=required_undo,
                status=ILLEGAL_ACTION_STATUS_OPEN,
            )
            session.add(item)
            await session.flush()
            finding_id = item.id
        return await self.get_illegal_action(finding_id)

    async def get_illegal_action(self, finding_id: str) -> PlayerIllegalAction | None:
        async with self._session_factory() as session:
            return await session.get(PlayerIllegalAction, finding_id)

    async def list_open_illegal_actions(
        self, session_id: str, player_id: str
    ) -> list[PlayerIllegalAction]:
        """The open findings against one seat, oldest first.

        Read on every invocation of that seat, which is what stops a seat
        outlasting a violation by ignoring one prompt.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(PlayerIllegalAction)
                .where(
                    PlayerIllegalAction.session_id == session_id,
                    PlayerIllegalAction.player_id == player_id,
                    PlayerIllegalAction.status == ILLEGAL_ACTION_STATUS_OPEN,
                )
                .order_by(PlayerIllegalAction.created_at, PlayerIllegalAction.id)
            )
            return list(result.scalars().unique())

    async def resolve_illegal_action(
        self, finding_id: str, *, resolution_note: str
    ) -> PlayerIllegalAction | None:
        """Close a finding, or return ``None`` when it was not open.

        Conditional on ``status = 'open'``, so a second resolve of the same
        finding is a no-op that reports itself as one rather than overwriting the
        note recorded by whoever resolved it first. ``None`` also covers a
        finding id that does not exist: both mean "there is nothing here to
        resolve", which is the same thing to tell the agent.
        """
        async with self._session_factory() as session, session.begin():
            now = utc_now()
            result = await session.execute(
                update(PlayerIllegalAction)
                .where(
                    PlayerIllegalAction.id == finding_id,
                    PlayerIllegalAction.status == ILLEGAL_ACTION_STATUS_OPEN,
                )
                .values(
                    status=ILLEGAL_ACTION_STATUS_RESOLVED,
                    resolution_note=resolution_note,
                    resolved_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount == 0:
                return None
        return await self.get_illegal_action(finding_id)

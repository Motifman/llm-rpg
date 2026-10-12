"""ExpectationRepository のインメモリ実装。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationEventNotFoundException,
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.repository.expectation_repository import (
    ExpectationRepository,
)
from ai_rpg_world.domain.memory.expectation.service.require_restorable import (
    require_restorable,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_snapshot import (
    ExpectationSnapshot,
)
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
)


@dataclass
class _BeingState:
    expectations: dict[ExpectationId, ExpectationSnapshot] = field(
        default_factory=dict
    )
    undelivered: list[UndeliveredExpectationEvent] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.expectations and not self.undelivered


def _require_being_id(being_id: object) -> BeingId:
    if not isinstance(being_id, BeingId):
        raise TypeError("being_id must be BeingId")
    return being_id


class InMemoryExpectationRepository(ExpectationRepository):
    """予期は保存用の値で持ち、読み出すたびに作り直す。

    取り出した予期を書き換えても、``save`` を通るまで保存先は変わらない。
    予期の状態と出来事を同じ保存の単位にするため。
    """

    def __init__(self) -> None:
        self._states: dict[BeingId, _BeingState] = {}

    def save(
        self,
        expectation: Expectation,
        events: Sequence[ExpectationEvent],
    ) -> None:
        if not isinstance(expectation, Expectation):
            raise TypeError("expectation must be Expectation")
        snapshot = expectation.snapshot()
        state = self._states.get(snapshot.holder, _BeingState())
        entries = [UndeliveredExpectationEvent.of(event) for event in events]
        previous = state.expectations.get(snapshot.expectation_id)
        closes_now = not snapshot.status.is_open and (
            previous is None or previous.status.is_open
        )
        if closes_now and not any(
            entry.event.turn == snapshot.closed_at_turn for entry in entries
        ):
            raise ExpectationValidationException(
                f"expectation {snapshot.expectation_id} closed at turn "
                f"{snapshot.closed_at_turn} as {snapshot.status.value}, "
                "but the event that closed it was not given"
            )
        for entry in entries:
            if (
                entry.event.expectation_id != snapshot.expectation_id
                or entry.event.holder != snapshot.holder
            ):
                raise ExpectationValidationException(
                    f"event {entry.event_id} does not belong to expectation "
                    f"{snapshot.expectation_id} held by {snapshot.holder}"
                )
        pending_ids = [u.event_id for u in state.undelivered] + [
            e.event_id for e in entries
        ]
        if len(set(pending_ids)) != len(pending_ids):
            duplicated = sorted(
                {str(i) for i in pending_ids if pending_ids.count(i) > 1}
            )
            raise ExpectationValidationException(
                f"events {duplicated} are already undelivered"
            )

        state.expectations[snapshot.expectation_id] = snapshot
        state.undelivered.extend(entries)
        self._states[snapshot.holder] = state

    def list_open_by_being(self, being_id: BeingId) -> list[Expectation]:
        return [
            Expectation.restore(snapshot)
            for snapshot in self._snapshots(being_id)
            if snapshot.status.is_open
        ]

    def list_all_by_being(self, being_id: BeingId) -> list[Expectation]:
        return [Expectation.restore(snapshot) for snapshot in self._snapshots(being_id)]

    def list_undelivered_by_being(
        self, being_id: BeingId
    ) -> list[UndeliveredExpectationEvent]:
        state = self._states.get(_require_being_id(being_id))
        return list(state.undelivered) if state else []

    def mark_delivered(self, being_id: BeingId, event_id: ExpectationEventId) -> None:
        state = self._states.get(_require_being_id(being_id))
        remaining = (
            [u for u in state.undelivered if u.event_id != event_id] if state else []
        )
        if state is None or len(remaining) == len(state.undelivered):
            raise ExpectationEventNotFoundException(
                f"event {event_id} is not undelivered for {being_id}"
            )
        state.undelivered = remaining
        self._drop_if_empty(being_id)

    def replace_all_by_being(
        self,
        being_id: BeingId,
        *,
        expectations: Sequence[Expectation],
        undelivered_events: Sequence[UndeliveredExpectationEvent],
        turn: int,
    ) -> None:
        _require_being_id(being_id)
        require_restorable(
            being_id,
            expectations=expectations,
            undelivered_events=undelivered_events,
            turn=turn,
        )
        replaced = _BeingState(
            expectations={
                snapshot.expectation_id: snapshot
                for snapshot in (e.snapshot() for e in expectations)
            },
            undelivered=list(undelivered_events),
        )
        self._states[being_id] = replaced
        self._drop_if_empty(being_id)

    def _snapshots(self, being_id: BeingId) -> list[ExpectationSnapshot]:
        state = self._states.get(_require_being_id(being_id))
        return list(state.expectations.values()) if state else []

    def _drop_if_empty(self, being_id: BeingId) -> None:
        state = self._states.get(being_id)
        if state is not None and state.is_empty():
            del self._states[being_id]


__all__ = ["InMemoryExpectationRepository"]

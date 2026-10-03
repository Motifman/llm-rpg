"""Being に戻す予期・未配信の出来事・記憶のターン数の組が、互いに食い違わないかを確かめる。

保存先が置き換える前と、snapshot の復元がどの保存先にも書く前の両方から呼ぶ。
復元は複数の保存先を順に書くので、ここで先に拒まないと、ほかの保存先だけが
書き換わったまま止まる。
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.turn import require_turn
from ai_rpg_world.domain.memory.expectation.value_object.undelivered_expectation_event import (
    UndeliveredExpectationEvent,
)


def require_restorable(
    being_id: BeingId,
    *,
    expectations: Sequence[Expectation],
    undelivered_events: Sequence[UndeliveredExpectationEvent],
    turn: int,
) -> None:
    """記憶のターン数は、予期を持ったターン・終わったターン・出来事のターンより前に戻らない。"""
    if not isinstance(being_id, BeingId):
        raise ExpectationValidationException("being_id must be BeingId")
    current = require_turn(turn, name="turn")
    held: set[ExpectationId] = set()
    for expectation in expectations:
        if not isinstance(expectation, Expectation):
            raise ExpectationValidationException("expectations must be Expectation")
        snapshot = expectation.snapshot()
        if snapshot.holder != being_id:
            raise ExpectationValidationException(
                f"expectation {snapshot.expectation_id} is held by "
                f"{snapshot.holder}, not {being_id}"
            )
        if snapshot.expectation_id in held:
            raise ExpectationValidationException(
                f"expectation {snapshot.expectation_id} appears twice"
            )
        held.add(snapshot.expectation_id)
        latest = max(snapshot.formed_at_turn, snapshot.closed_at_turn or 0)
        if current < latest:
            raise ExpectationValidationException(
                f"turn ({current}) is before expectation {snapshot.expectation_id} "
                f"(formed or closed at {latest})"
            )
    seen: set[ExpectationEventId] = set()
    for entry in undelivered_events:
        if not isinstance(entry, UndeliveredExpectationEvent):
            raise ExpectationValidationException(
                "undelivered_events must be UndeliveredExpectationEvent"
            )
        if entry.event.holder != being_id:
            raise ExpectationValidationException(
                f"event {entry.event_id} is held by {entry.event.holder}, not {being_id}"
            )
        if entry.event_id in seen:
            raise ExpectationValidationException(
                f"event {entry.event_id} appears twice"
            )
        seen.add(entry.event_id)
        if entry.event.expectation_id not in held:
            raise ExpectationValidationException(
                f"event {entry.event_id} has no expectation {entry.event.expectation_id}"
            )
        if current < entry.event.turn:
            raise ExpectationValidationException(
                f"turn ({current}) is before event {entry.event_id}"
            )


__all__ = ["require_restorable"]

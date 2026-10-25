"""保存した集約がためたイベントを、組み立てるときに渡された配り手へ渡す (design_decisions D1837 の 6)。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ai_rpg_world.eventing import AggregateRoot, DomainEvent

EventHandoff = Callable[[Sequence[DomainEvent]], None]


def save_and_hand_off(aggregate: AggregateRoot[Any], handoff: EventHandoff | None, store: Callable[[], None]) -> None:
    """保存を確定の区切りとし、保存してから、ためたイベントを取り出して空にして配る。

    配り手の無い保存先にイベントのたまった集約を保存しようとしたら、保存する前に止める。黙って
    捨てると、受け手を足したときに届かない理由が分からなくなる。
    """
    events = aggregate.get_events()
    if not events:
        store()
        return
    if handoff is None:
        raise RuntimeError(
            f"{type(aggregate).__name__} has {len(events)} pending event(s) but the repository has no handoff"
        )
    store()
    aggregate.clear_events()
    handoff(events)


__all__ = ["EventHandoff", "save_and_hand_off"]

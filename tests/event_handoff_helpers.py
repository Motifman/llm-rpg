"""Being の保存先に渡す配り手の、試験用の部品。"""

from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.eventing import DomainEvent


def discard_events(events: Sequence[DomainEvent]) -> None:
    """配り手そのものを試験しない試験で、保存した集約のイベントを受け取って捨てる。"""


__all__ = ["discard_events"]

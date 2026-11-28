from __future__ import annotations

from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository, AcquaintanceRoster
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.event_handoff import EventHandoff, save_and_hand_off


def _require_roster(roster: object) -> AcquaintanceRoster:
    if not isinstance(roster, AcquaintanceRoster):
        raise TypeError("roster must be AcquaintanceRoster")
    return roster


def _copy(roster: AcquaintanceRoster) -> AcquaintanceRoster:
    """記録は中身の変わらない値なので、同じ記録を持つ新しい集約を作れば写しになる。ためたイベントは写さない。"""
    return AcquaintanceRoster(roster.being_id, acquaintances=roster.acquaintances)


class InMemoryAcquaintanceRepository(AcquaintanceRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self, *, handoff: EventHandoff | None = None) -> None:
        self._by_being: dict[BeingId, AcquaintanceRoster] = {}
        self._handoff = handoff

    def get(self, being_id: BeingId) -> AcquaintanceRoster:
        stored = self._by_being.get(being_id)
        return AcquaintanceRoster.empty(being_id) if stored is None else _copy(stored)

    def save(self, roster: AcquaintanceRoster) -> None:
        _require_roster(roster)

        def store() -> None:
            self._by_being[roster.being_id] = _copy(roster)

        save_and_hand_off(roster, self._handoff, store)

    def replace_all_by_being(self, roster: AcquaintanceRoster) -> None:
        if not _require_roster(roster).acquaintances:
            self._by_being.pop(roster.being_id, None)
            return
        self.save(roster)


__all__ = ["InMemoryAcquaintanceRepository"]

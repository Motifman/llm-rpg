from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.domain.acquaintance import (
    Acquaintance,
    AcquaintanceInvalid,
    AcquaintanceRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

_Key = tuple[str, str]


class InMemoryAcquaintanceRepository(AcquaintanceRepository):
    def __init__(self) -> None:
        self._by_being: dict[BeingId, dict[_Key, Acquaintance]] = {}

    def record_meeting(
        self, being_id: BeingId, *, environment_name: str, name: str, turn: int
    ) -> Acquaintance:
        book = self._by_being.setdefault(being_id, {})
        key = (environment_name, name)
        known = book.get(key)
        met = (
            Acquaintance.first_meeting(
                environment_name=environment_name, name=name, turn=turn
            )
            if known is None
            else known.met_at(turn=turn)
        )
        book[key] = met
        return met

    def record_introduction(
        self,
        being_id: BeingId,
        *,
        environment_name: str,
        name: str,
        turn: int,
        relation_note: str | None,
    ) -> Acquaintance:
        book = self._by_being.setdefault(being_id, {})
        key = (environment_name, name)
        known = book.get(key)
        if known is not None:
            return known
        introduced = Acquaintance.introduced(
            environment_name=environment_name,
            name=name,
            turn=turn,
            relation_note=relation_note,
        )
        book[key] = introduced
        return introduced

    def find(
        self, being_id: BeingId, *, environment_name: str, name: str
    ) -> Acquaintance | None:
        return self._by_being.get(being_id, {}).get((environment_name, name))

    def list_by_being(self, being_id: BeingId) -> tuple[Acquaintance, ...]:
        return tuple(self._by_being.get(being_id, {}).values())

    def replace_all_by_being(
        self, being_id: BeingId, acquaintances: Sequence[Acquaintance]
    ) -> None:
        book: dict[_Key, Acquaintance] = {}
        for acquaintance in acquaintances:
            key = (acquaintance.environment_name, acquaintance.name)
            if key in book:
                raise AcquaintanceInvalid(f"duplicate acquaintance: {key}")
            book[key] = acquaintance
        self._by_being[being_id] = book


__all__ = ["InMemoryAcquaintanceRepository"]

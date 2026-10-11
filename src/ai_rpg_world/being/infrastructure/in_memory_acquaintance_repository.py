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
        self,
        being_id: BeingId,
        *,
        environment_name: str,
        name: str,
        turn: int,
        knows_name: bool = True,
    ) -> Acquaintance:
        book = self._by_being.setdefault(being_id, {})
        key = (environment_name, name)
        known = book.get(key)
        met = (
            Acquaintance.first_meeting(
                environment_name=environment_name,
                name=name,
                turn=turn,
                knows_name=knows_name,
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
            # 名前を知らずに会った相手を紹介されたら、名前を知る。関係の注記は紹介でだけ付く
            # 決まり (D1520) だが、会ったあとの紹介では付けない。
            named = known.learned_name(turn=turn)
            book[key] = named
            return named
        introduced = Acquaintance.introduced(
            environment_name=environment_name,
            name=name,
            turn=turn,
            relation_note=relation_note,
        )
        book[key] = introduced
        return introduced

    def record_name_learned(
        self, being_id: BeingId, *, environment_name: str, name: str, turn: int
    ) -> Acquaintance | None:
        book = self._by_being.get(being_id, {})
        key = (environment_name, name)
        known = book.get(key)
        if known is None:
            return None
        named = known.learned_name(turn=turn)
        book[key] = named
        return named

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

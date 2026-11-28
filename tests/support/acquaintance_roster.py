"""知り合いの名簿を用意する試験で、名簿を引いて書き換えて保存する 3 行を 1 行にする。"""

from __future__ import annotations

from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.being_id import BeingId


def meet(
    store: AcquaintanceRepository,
    being_id: BeingId,
    *,
    environment_name: str,
    name: str,
    turn: int,
    knows_name: bool = True,
) -> None:
    roster = store.get(being_id)
    roster.meet(environment_name=environment_name, name=name, turn=turn, knows_name=knows_name)
    store.save(roster)


def introduce(
    store: AcquaintanceRepository,
    being_id: BeingId,
    *,
    environment_name: str,
    name: str,
    turn: int,
    relation_note: str | None,
) -> None:
    roster = store.get(being_id)
    roster.introduce(environment_name=environment_name, name=name, turn=turn, relation_note=relation_note)
    store.save(roster)


def learn_name(
    store: AcquaintanceRepository, being_id: BeingId, *, environment_name: str, name: str, turn: int
) -> None:
    roster = store.get(being_id)
    roster.learn_name(environment_name=environment_name, name=name, turn=turn)
    store.save(roster)

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.acquaintance import AcquaintanceMetEvent, AcquaintanceRoster
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.eventing import DomainEvent
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being_ada")
KAI = BeingId("being_kai")


def _roster(being_id: BeingId = ADA, name: str = "ノア") -> AcquaintanceRoster:
    roster = AcquaintanceRoster.empty(being_id)
    roster.meet(environment_name="島", name=name, turn=1)
    return roster


def _names(roster: AcquaintanceRoster) -> list[str]:
    return [a.name for a in roster.acquaintances]


class TestInMemoryAcquaintanceRepository:
    """InMemoryAcquaintanceRepository が、Being ごとに知り合いの名簿を 1 つ持ち、丸ごと置き換えることを保証する。"""

    def test_a_being_without_acquaintances_gets_an_empty_roster(self) -> None:
        """まだ何も保存していない Being には、その Being の空の名簿を返す。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)

        roster = repository.get(ADA)

        assert (roster.being_id, roster.acquaintances) == (ADA, ())

    def test_saved_roster_comes_back_only_for_its_being(self) -> None:
        """保存した名簿は持ち主の Being にだけ返り、別の Being は空のまま。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)

        repository.save(_roster())

        assert (_names(repository.get(ADA)), repository.get(KAI).acquaintances) == (["ノア"], ())

    def test_replace_all_with_an_empty_roster_leaves_no_acquaintance(self) -> None:
        """持ち越しから空の名簿で戻すと、前に保存した記録は残らず、別の Being の記録には触れない。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)
        repository.save(_roster())
        repository.save(_roster(KAI, "リオ"))

        repository.replace_all_by_being(AcquaintanceRoster.empty(ADA))

        assert (repository.get(ADA).acquaintances, _names(repository.get(KAI))) == ((), ["リオ"])

    def test_replace_all_puts_the_given_roster(self) -> None:
        """持ち越しから戻すと、渡した名簿がそのまま入る。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)

        repository.replace_all_by_being(_roster())

        assert _names(repository.get(ADA)) == ["ノア"]


class TestTheRepositoryHandsOutCopies:
    """InMemoryAcquaintanceRepository が、出し入れのたびに写しを渡し、save し忘れた書き換えを保存したように見せないことを保証する。"""

    def test_changing_a_roster_without_saving_keeps_the_stored_one(self) -> None:
        """get した名簿で会っても、save しなければ、次の get は会う前の名簿を返す。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)
        repository.save(_roster())

        repository.get(ADA).meet(environment_name="島", name="リオ", turn=2)

        assert _names(repository.get(ADA)) == ["ノア"]

    def test_changing_a_roster_after_saving_keeps_the_stored_one(self) -> None:
        """save したあとで渡した名簿を書き換えても、保存先は save した時点のまま。"""
        repository = InMemoryAcquaintanceRepository(handoff=discard_events)
        roster = _roster()
        repository.save(roster)

        roster.meet(environment_name="島", name="リオ", turn=2)

        assert _names(repository.get(ADA)) == ["ノア"]


class TestHandingOffEvents:
    """InMemoryAcquaintanceRepository が、保存した名簿がためたイベントを配り手に渡すことを保証する。"""

    def test_save_hands_off_pending_events_and_clears_them(self) -> None:
        """会ったあとの名簿を保存すると、AcquaintanceMetEvent が 1 件配り手に渡り、名簿のイベントは空になる。"""
        handed: list[DomainEvent] = []
        repository = InMemoryAcquaintanceRepository(handoff=handed.extend)
        roster = _roster()

        repository.save(roster)

        assert [type(e) for e in handed] == [AcquaintanceMetEvent]
        assert roster.get_events() == []

    def test_saving_events_without_a_handoff_is_refused_before_storing(self) -> None:
        """配り手の無い保存先にイベントのたまった名簿を保存すると止まり、保存先は空のまま。"""
        repository = InMemoryAcquaintanceRepository()

        with pytest.raises(RuntimeError):
            repository.save(_roster())

        assert repository.get(ADA).acquaintances == ()

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being-ada")
BEN = BeingId("being-ben")


def _memory(being_id: BeingId = ADA, flow: str = "坑道の奥で鍵を探していた") -> ShortTermMemory:
    memory = ShortTermMemory.empty(being_id)
    memory.add_backstory(Backstory(flow=flow, mood="", written_turn=20))
    return memory


def _observation() -> Observation:
    return Observation(
        body="鐘が鳴った",
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


def _flows(memory: ShortTermMemory) -> list[str]:
    return [b.flow for b in memory.backstories]


class TestInMemoryShortTermMemoryRepository:
    """InMemoryShortTermMemoryRepository が、Being ごとに短期記憶を 1 つ持ち、丸ごと置き換えることを保証する。"""

    def test_a_being_without_memory_gets_an_empty_one(self) -> None:
        """まだ何も保存していない Being には、その Being の空の短期記憶を返す。"""
        repository = InMemoryShortTermMemoryRepository()

        memory = repository.get(ADA)

        assert (memory.being_id, memory.is_empty()) == (ADA, True)

    def test_saved_memory_comes_back_only_for_its_being(self) -> None:
        """保存した短期記憶は持ち主の Being にだけ返り、別の Being は空のまま。"""
        repository = InMemoryShortTermMemoryRepository()

        repository.save(_memory())

        assert (_flows(repository.get(ADA)), repository.get(BEN).is_empty()) == (["坑道の奥で鍵を探していた"], True)

    def test_save_replaces_the_whole_memory(self) -> None:
        """もう一度保存すると、前の短期記憶を丸ごと置き換える。"""
        repository = InMemoryShortTermMemoryRepository()
        repository.save(_memory())

        repository.save(_memory(flow="水門を見に行った"))

        assert _flows(repository.get(ADA)) == ["水門を見に行った"]

    def test_replace_all_with_an_empty_memory_leaves_nothing(self) -> None:
        """持ち越しから空の短期記憶で戻すと、前に保存したものは残らず、空の短期記憶を返す。"""
        repository = InMemoryShortTermMemoryRepository()
        repository.save(_memory())

        repository.replace_all_by_being(ShortTermMemory.empty(ADA))

        assert repository.get(ADA).is_empty()

    def test_replace_all_puts_the_given_memory(self) -> None:
        """持ち越しから戻すと、渡した短期記憶がそのまま入る。"""
        repository = InMemoryShortTermMemoryRepository()

        repository.replace_all_by_being(_memory())

        assert _flows(repository.get(ADA)) == ["坑道の奥で鍵を探していた"]

    @pytest.mark.parametrize("method", ["save", "replace_all_by_being"])
    def test_non_memory_value_is_rejected(self, method: str) -> None:
        """短期記憶でない値を保存しようとすると TypeError を投げ、何も保存しない。"""
        repository = InMemoryShortTermMemoryRepository()

        with pytest.raises(TypeError):
            getattr(repository, method)({"events": []})
        assert repository.get(ADA).is_empty()


class TestCopies:
    """保存先が出し入れのたびに写しを渡し、呼び手の書き換えが save するまで保存先に届かないことを保証する。"""

    def test_changes_to_a_fetched_memory_are_not_stored_until_saved(self) -> None:
        """取り出した集約に観測を足しても、save するまで保存先の中身は変わらない。"""
        repository = InMemoryShortTermMemoryRepository()
        repository.save(_memory())
        fetched = repository.get(ADA)

        fetched.perceive(_observation(), current_turn=0)

        assert repository.get(ADA).experiences == ()

    def test_changes_after_save_are_not_stored(self) -> None:
        """save したあとで同じ集約に観測を足しても、保存先の中身は変わらない。"""
        repository = InMemoryShortTermMemoryRepository()
        memory = _memory()
        repository.save(memory)

        memory.perceive(_observation(), current_turn=0)

        assert repository.get(ADA).experiences == ()

    def test_pending_events_are_not_stored(self) -> None:
        """ためたイベントは保存しない。取り出した集約はイベントを持たないので、同じイベントを 2 度渡さない。"""
        repository = InMemoryShortTermMemoryRepository()
        memory = ShortTermMemory.empty(ADA)
        memory.perceive(_observation(), current_turn=0)
        memory.fold(current_turn=20)
        assert len(memory.get_events()) == 1

        repository.save(memory)

        assert repository.get(ADA).get_events() == []
        assert len(memory.get_events()) == 1

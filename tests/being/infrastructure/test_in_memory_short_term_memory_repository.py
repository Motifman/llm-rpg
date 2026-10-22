from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being-ada")
BEN = BeingId("being-ben")


def _memory(flow: str = "坑道の奥で鍵を探していた") -> ShortTermMemory:
    return ShortTermMemory.empty().add_backstory(Backstory(flow=flow, mood="", written_turn=20))


class TestInMemoryShortTermMemoryRepository:
    """InMemoryShortTermMemoryRepository が、Being ごとに短期記憶を 1 つ持ち、丸ごと置き換えることを保証する。"""

    def test_a_being_without_memory_gets_an_empty_one(self) -> None:
        """まだ何も保存していない Being には、空の短期記憶を返す。"""
        repository = InMemoryShortTermMemoryRepository()

        assert repository.get(ADA) == ShortTermMemory.empty()

    def test_saved_memory_comes_back_only_for_its_being(self) -> None:
        """保存した短期記憶はその Being にだけ返り、別の Being は空のまま。"""
        repository = InMemoryShortTermMemoryRepository()

        repository.save(ADA, _memory())

        assert (repository.get(ADA), repository.get(BEN)) == (_memory(), ShortTermMemory.empty())

    def test_save_replaces_the_whole_memory(self) -> None:
        """もう一度保存すると、前の短期記憶を丸ごと置き換える。"""
        repository = InMemoryShortTermMemoryRepository()
        repository.save(ADA, _memory())

        repository.save(ADA, _memory("水門を見に行った"))

        assert [b.flow for b in repository.get(ADA).backstories] == ["水門を見に行った"]

    def test_replace_all_with_an_empty_memory_leaves_nothing(self) -> None:
        """持ち越しから空の短期記憶で戻すと、前に保存したものは残らず、空の短期記憶を返す。"""
        repository = InMemoryShortTermMemoryRepository()
        repository.save(ADA, _memory())

        repository.replace_all_by_being(ADA, ShortTermMemory.empty())

        assert repository.get(ADA) == ShortTermMemory.empty()

    def test_replace_all_puts_the_given_memory(self) -> None:
        """持ち越しから戻すと、渡した短期記憶がそのまま入る。"""
        repository = InMemoryShortTermMemoryRepository()

        repository.replace_all_by_being(ADA, _memory())

        assert repository.get(ADA) == _memory()

    @pytest.mark.parametrize("method", ["save", "replace_all_by_being"])
    def test_non_memory_value_is_rejected(self, method: str) -> None:
        """短期記憶でない値を保存しようとすると TypeError を投げ、何も保存しない。"""
        repository = InMemoryShortTermMemoryRepository()

        with pytest.raises(TypeError):
            getattr(repository, method)(ADA, {"events": []})
        assert repository.get(ADA) == ShortTermMemory.empty()

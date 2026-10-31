from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.being.application.add_backstory_to_short_term_memory import (
    AddBackstoryToShortTermMemory,
    AddBackstoryToShortTermMemoryCommand,
)
from ai_rpg_world.being.application.write_backstory import WriteBackstory, WriteBackstoryCommand
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.short_term_memory import (
    Backstory,
    Experience,
    Perception,
    ShortTermMemoryBackstoryAddedEvent,
)
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import ShortTermMemoryStaleBackstoryException
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")


def _seen(turn: int) -> Perception:
    observation = Observation(
        body=f"ターン {turn} の出来事",
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )
    return Perception(turn=turn, observation=observation)


class _Writer(BackstoryWriter):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write(
        self,
        *,
        self_name: str,
        persona: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> Backstory:
        self.calls.append(
            {
                "self_name": self_name,
                "persona": persona,
                "experiences": experiences,
                "previous": previous,
                "until_turn": until_turn,
                "written_turn": written_turn,
            }
        )
        return Backstory(flow="鐘のあと扉が開いた", mood="", written_turn=written_turn, until_turn=until_turn)


class TestWriteBackstory:
    """WriteBackstory が、コマンドの材料をいきさつの書き手に渡し、書いたいきさつを返すことを保証する。"""

    def test_command_is_passed_to_the_writer_and_the_backstory_is_returned(self) -> None:
        """名前・人格の文・まとめる出来事・前のいきさつ・範囲の終わり・書いたターンをそのまま書き手に渡し、書き手が返したいきさつを返す。"""
        writer = _Writer()
        previous = Backstory(flow="前の流れ", mood="", written_turn=0, until_turn=0)
        command = WriteBackstoryCommand(
            being_id=ADA,
            self_name="エイダ",
            persona="慎重",
            experiences=(_seen(1), _seen(2)),
            previous=previous,
            until_turn=10,
            written_turn=20,
        )

        backstory = WriteBackstory(writer).execute(command)

        assert writer.calls == [
            {
                "self_name": "エイダ",
                "persona": "慎重",
                "experiences": (_seen(1), _seen(2)),
                "previous": previous,
                "until_turn": 10,
                "written_turn": 20,
            }
        ]
        assert backstory == Backstory(flow="鐘のあと扉が開いた", mood="", written_turn=20, until_turn=10)


class TestAddBackstoryToShortTermMemory:
    """AddBackstoryToShortTermMemory が、いきさつを短期記憶に入れて保存し、古い範囲のいきさつは断ることを保証する。"""

    def test_backstory_is_added_and_saved(self) -> None:
        """いきさつを入れて保存すると、保存先の短期記憶にいきさつが入り、いきさつが入ったイベントが配送器に渡る。"""
        handed: list[object] = []
        store = InMemoryShortTermMemoryRepository(handoff=handed.extend)
        backstory = Backstory(flow="流れ", mood="", written_turn=20, until_turn=10)

        AddBackstoryToShortTermMemory(store).execute(
            AddBackstoryToShortTermMemoryCommand(being_id=ADA, backstory=backstory)
        )

        assert store.get(ADA).backstories == (backstory,)
        assert [type(e) for e in handed] == [ShortTermMemoryBackstoryAddedEvent]

    def test_stale_backstory_is_refused_and_nothing_is_saved(self) -> None:
        """いま持っているいきさつと同じ範囲までのいきさつは ShortTermMemoryStaleBackstoryException で断り、保存も配送器への受け渡しもしない。"""
        handed: list[object] = []
        store = InMemoryShortTermMemoryRepository(handoff=handed.extend)
        use_case = AddBackstoryToShortTermMemory(store)
        first = Backstory(flow="先に届いた", mood="", written_turn=20, until_turn=10)
        use_case.execute(AddBackstoryToShortTermMemoryCommand(being_id=ADA, backstory=first))
        handed.clear()

        with pytest.raises(ShortTermMemoryStaleBackstoryException):
            use_case.execute(
                AddBackstoryToShortTermMemoryCommand(
                    being_id=ADA, backstory=Backstory(flow="遅れて届いた", mood="", written_turn=30, until_turn=10)
                )
            )

        assert (store.get(ADA).backstories, handed) == ((first,), [])

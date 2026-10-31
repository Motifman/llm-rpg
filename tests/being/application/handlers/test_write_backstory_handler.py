from __future__ import annotations

from typing import Any

from ai_rpg_world.being.application.add_backstory_to_short_term_memory import AddBackstoryToShortTermMemoryCommand
from ai_rpg_world.being.application.handlers.write_backstory_handler import WriteBackstoryHandler
from ai_rpg_world.being.application.write_backstory import WriteBackstoryCommand
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter, WrittenBackstory
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import (
    Backstory,
    Experience,
    ShortTermMemory,
    ShortTermMemoryBackstoryOverdueEvent,
    ShortTermMemoryRangeFilledEvent,
)
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AsyncEventHandler
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being_p1")
PREVIOUS = Backstory(flow="前の流れ", mood="", written_turn=0, until_turn=0)


def _seen(body: str) -> Observation:
    return Observation(
        body=body,
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


class _Writer(BackstoryWriter):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write(
        self,
        *,
        persona: Persona,
        persona_text: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> WrittenBackstory:
        self.calls.append({"persona": persona, "experiences": experiences})
        return WrittenBackstory(
            backstory=Backstory(
                flow=f"{len(experiences)} 件の流れ", mood="", written_turn=written_turn, until_turn=until_turn
            ),
            truncated={"mood": 130},
        )


def _memory_with_filled_range() -> ShortTermMemory:
    """いきさつを 1 つ持ち、ターン 20 で範囲が埋まった短期記憶。ためたイベントは範囲が埋まったイベントだけ。"""
    memory = ShortTermMemory.empty(ADA)
    memory.add_backstory(PREVIOUS)
    for turn in range(0, 20):
        memory.perceive(_seen(f"ターン {turn + 1} の出来事"), current_turn=turn)
    memory.clear_events()
    memory.end_turn(turn=20)
    return memory


class _World:
    def __init__(self) -> None:
        self.store = InMemoryShortTermMemoryRepository(handoff=discard_events)
        self.writer = _Writer()
        self.looked_up: list[BeingId] = []
        self.text_looked_up: list[BeingId] = []
        self.handler = WriteBackstoryHandler(
            writer=self.writer,
            store=self.store,
            persona_of=lambda being_id: (
                self.looked_up.append(being_id),
                Persona(name="エイダ", first_person="わたし"),
            )[1],
            persona_text_of=lambda being_id: (self.text_looked_up.append(being_id), "慎重")[1],
        )


class TestPrepare:
    """WriteBackstoryHandler.prepare が、イベントから材料を取り出し、Being の人柄とゲームの側の人格の文を引いてコマンドを作ることを保証する。"""

    def test_range_filled_becomes_a_write_command(self) -> None:
        """範囲が埋まったイベントから、Being の保存先から引いた人柄、ゲームの側の関数で引いた人格の文、まとめる出来事、いちばん新しいいきさつ、範囲の終わり、埋まったターンを持つ WriteBackstoryCommand を作る。"""
        world = _World()
        (event,) = _memory_with_filled_range().get_events()
        assert isinstance(event, ShortTermMemoryRangeFilledEvent)

        command = world.handler.prepare(event)

        assert command == WriteBackstoryCommand(
            being_id=ADA,
            persona=Persona(name="エイダ", first_person="わたし"),
            persona_text="慎重",
            experiences=event.experiences,
            previous=PREVIOUS,
            until_turn=10,
            written_turn=20,
        )
        assert (world.looked_up, world.text_looked_up) == ([ADA], [ADA])

    def test_overdue_becomes_a_write_command_for_the_same_range(self) -> None:
        """いきさつが遅れているイベントからも、同じ範囲を書き直すコマンドを作る。書いたターンは遅れを知らせたターン。"""
        world = _World()
        memory = _memory_with_filled_range()
        memory.clear_events()
        memory.end_turn(turn=30)
        (event,) = memory.get_events()
        assert isinstance(event, ShortTermMemoryBackstoryOverdueEvent)

        command = world.handler.prepare(event)

        assert (command.until_turn, command.written_turn, len(command.experiences)) == (10, 30, 10)


class TestHandleAndApply:
    """WriteBackstoryHandler.handle がいきさつを書いて記憶に入れるコマンドにし、apply がそれを記憶に入れることを保証する。"""

    def test_handle_writes_and_returns_a_command_to_add_it(self) -> None:
        """handle はいきさつを書き、その Being にそのいきさつを入れる AddBackstoryToShortTermMemoryCommand を、切り詰めた項目とともに返す。短期記憶はまだ変えない。"""
        world = _World()
        (event,) = _memory_with_filled_range().get_events()

        command = world.handler.handle(world.handler.prepare(event))

        assert command == AddBackstoryToShortTermMemoryCommand(
            being_id=ADA,
            backstory=Backstory(flow="10 件の流れ", mood="", written_turn=20, until_turn=10),
            truncated={"mood": 130},
        )
        assert world.store.get(ADA).backstories == ()

    def test_apply_adds_the_backstory_to_the_short_term_memory(self) -> None:
        """apply は、そのいきさつを保存先の短期記憶に入れる。"""
        world = _World()
        world.store.save(_memory_with_filled_range())
        backstory = Backstory(flow="流れ", mood="", written_turn=20, until_turn=10)

        world.handler.apply(AddBackstoryToShortTermMemoryCommand(being_id=ADA, backstory=backstory))

        assert world.store.get(ADA).backstories == (PREVIOUS, backstory)

    def test_handler_is_an_async_event_handler(self) -> None:
        """イベント基盤の非同期のハンドラの基底を継ぐ (design_decisions D1824-15)。"""
        assert isinstance(_World().handler, AsyncEventHandler)

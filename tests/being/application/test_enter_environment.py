from __future__ import annotations

import pytest

from ai_rpg_world.being.application.enter_environment import EnterEnvironment, EnterEnvironmentCommand
from ai_rpg_world.being.contract import EnvironmentEntry, Introduction
from ai_rpg_world.being.domain.acquaintance import Acquaintance, HowKnown
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_being_repository import InMemoryBeingRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIntroducedToItselfException,
    BeingNotFoundException,
)

GEN = BeingId("gen")
MINE = "廃坑の山村"


class _Parts:
    def __init__(self) -> None:
        self.beings = InMemoryBeingRepository()
        self.acquaintances = InMemoryAcquaintanceRepository()
        self.clock = InMemoryMemoryTurnClock()
        self.enter = EnterEnvironment(self.beings, self.acquaintances, self.clock)

    def prepare_gen(self) -> None:
        self.beings.save(Being(GEN, Persona(name="ゲン")))


class TestEnterEnvironment:
    """EnterEnvironment が、Being を環境に入れ、取り決めの紹介を知り合いとして記録することを保証する。"""

    def test_being_is_attached_to_the_environment(self) -> None:
        """入ると、Being は環境の識別子と取り決めの環境の名前で、その環境に入っている。"""
        parts = _Parts()
        parts.prepare_gen()

        parts.enter.execute(
            EnterEnvironmentCommand(
                being_id=GEN, environment_id="mine#1", entry=EnvironmentEntry(environment_name=MINE)
            )
        )

        entered = parts.beings.find_by_id(GEN)
        assert entered is not None
        assert entered.attachment == BeingAttachment(environment_id="mine#1", environment_name=MINE)

    def test_introduced_people_are_known_from_the_current_turn(self) -> None:
        """紹介にサヨが入っていると、サヨは記憶のいまのターン (3) から紹介で知った相手として記録され、ほかの相手は記録されない。"""
        parts = _Parts()
        parts.prepare_gen()
        for _ in range(3):
            parts.clock.advance_turn(GEN)

        parts.enter.execute(
            EnterEnvironmentCommand(
                being_id=GEN,
                environment_id="mine#1",
                entry=EnvironmentEntry(environment_name=MINE, introductions=(Introduction(name="サヨ"),)),
            )
        )

        [sayo] = parts.acquaintances.list_by_being(GEN)
        assert (sayo.environment_name, sayo.name, sayo.how_known, sayo.known_since_turn) == (
            MINE,
            "サヨ",
            HowKnown.INTRODUCED,
            3,
        )

    def test_introduction_to_itself_is_refused_without_attaching_or_recording(self) -> None:
        """紹介に自分の名前「ゲン」があると BeingIntroducedToItselfException を投げ、環境に入らず、知り合いも記録しない。"""
        parts = _Parts()
        parts.prepare_gen()

        with pytest.raises(BeingIntroducedToItselfException):
            parts.enter.execute(
                EnterEnvironmentCommand(
                    being_id=GEN,
                    environment_id="mine#1",
                    entry=EnvironmentEntry(environment_name=MINE, introductions=(Introduction(name="ゲン"),)),
                )
            )

        entered = parts.beings.find_by_id(GEN)
        assert entered is not None
        assert entered.attachment is None
        assert parts.acquaintances.list_by_being(GEN) == ()

    def test_unprepared_being_is_refused(self) -> None:
        """用意していない Being を入れようとすると BeingNotFoundException を投げる。"""
        parts = _Parts()

        with pytest.raises(BeingNotFoundException):
            parts.enter.execute(
                EnterEnvironmentCommand(
                    being_id=GEN, environment_id="mine#1", entry=EnvironmentEntry(environment_name=MINE)
                )
            )

    def test_failed_introduction_leaves_being_outside_so_the_same_command_can_be_retried(self) -> None:
        """紹介の記録で失敗すると、Being は環境に入らないまま残り、同じコマンドをやり直すと入れて紹介も 1 件だけ記録される。"""
        parts = _Parts()
        parts.prepare_gen()
        failing = _FailsOnce(parts.acquaintances)
        command = EnterEnvironmentCommand(
            being_id=GEN,
            environment_id="mine#1",
            entry=EnvironmentEntry(environment_name=MINE, introductions=(Introduction(name="サヨ"),)),
        )

        with pytest.raises(RuntimeError):
            EnterEnvironment(parts.beings, failing, parts.clock).execute(command)
        left = parts.beings.find_by_id(GEN)
        EnterEnvironment(parts.beings, failing, parts.clock).execute(command)

        assert left is not None
        assert left.attachment is None
        entered = parts.beings.find_by_id(GEN)
        assert entered is not None
        assert entered.attachment == BeingAttachment(environment_id="mine#1", environment_name=MINE)
        assert [a.name for a in parts.acquaintances.list_by_being(GEN)] == ["サヨ"]


class _FailsOnce(InMemoryAcquaintanceRepository):
    def __init__(self, store: InMemoryAcquaintanceRepository) -> None:
        super().__init__()
        self._store = store
        self._failed = False

    def record_introduction(
        self, being_id: BeingId, *, environment_name: str, name: str, turn: int, relation_note: str | None
    ) -> Acquaintance:
        if not self._failed:
            self._failed = True
            raise RuntimeError("acquaintance store is unavailable")
        return self._store.record_introduction(
            being_id, environment_name=environment_name, name=name, turn=turn, relation_note=relation_note
        )

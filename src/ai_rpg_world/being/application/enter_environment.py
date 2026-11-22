from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.contract import EnvironmentEntry
from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.being_repository import BeingRepository
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.domain.being.exception.being_exceptions import BeingNotFoundException


@dataclass(frozen=True)
class EnterEnvironmentCommand:
    being_id: BeingId
    environment_id: str
    entry: EnvironmentEntry


class EnterEnvironment:
    def __init__(
        self, beings: BeingRepository, acquaintances: AcquaintanceRepository, turn_reader: MemoryTurnReader
    ) -> None:
        self._beings = beings
        self._acquaintances = acquaintances
        self._turn_reader = turn_reader

    def execute(self, command: EnterEnvironmentCommand) -> None:
        being = self._beings.find_by_id(command.being_id)
        if being is None:
            raise BeingNotFoundException(f"Being({command.being_id}) is not prepared")
        being.enter(command.environment_id, command.entry)
        turn = self._turn_reader.current_turn(command.being_id)
        # 入ったことを先に保存すると、紹介の記録で失敗したとき、同じコマンドをやり直しても入り直せず断られる。
        # 紹介の記録は知っている相手を変えないので、やり直しても重ならない
        for introduction in command.entry.introductions:
            self._acquaintances.record_introduction(
                command.being_id,
                environment_name=command.entry.environment_name,
                name=introduction.name,
                turn=turn,
                relation_note=introduction.relation_note,
            )
        self._beings.save(being)


__all__ = ["EnterEnvironment", "EnterEnvironmentCommand"]

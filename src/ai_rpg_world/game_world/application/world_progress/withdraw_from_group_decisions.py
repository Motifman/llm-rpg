from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class WithdrawFromGroupDecisionsCommand:
    person: PersonId


@final
class WithdrawFromGroupDecisions:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: WithdrawFromGroupDecisionsCommand) -> None:
        def work(session: WorldSession) -> None:
            world = session.aggregates()
            # 倒れた同じ確定で死ぬこともあるので、イベントの種類ではなく確定したいまの体の状態で外し方を決める。
            life_state = world.vitals(command.person).life_state()
            for declaration in session.facts().nouns().all_group_decisions():
                world.group_decision(declaration).withdraw_person(command.person, life_state)

        self._scope.run(work)

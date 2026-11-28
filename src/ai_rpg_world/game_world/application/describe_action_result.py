from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, OwnActionResult, TextWithPeople
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.take_chosen_action import TurnGuidance
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class DescribeActionResultCommand:
    reply: ActionReply | TurnGuidance
    call_id: str


@final
class DescribeActionResult:
    def __init__(self, scope: CommandScope, design: WorldDesign, day_night: DayNightDeclaration) -> None:
        self._scope = scope
        self._day_night = day_night
        self._clock = design.clock_wording

    def __call__(self, command: DescribeActionResultCommand) -> Observation:
        # 本文と要約の呼び名と時刻を、同じ時点の世界から作る
        body, summary, time = self._scope.run(lambda session: self._read(session, command.reply))
        return Observation(
            body=body,
            route=OwnActionResult(call_id=command.call_id, succeeded=command.reply.succeeded(), action_summary=summary),
            time=time,
            subject_is_self=True,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=True,
        )

    def _read(
        self, session: WorldSession, reply: ActionReply | TurnGuidance
    ) -> tuple[str | TextWithPeople, TextWithPeople | None, ObservedTime]:
        view = WorldPerceptionSenses(session.facts()).view_for(reply.actor())
        time = self._clock.observed_time_at(session.clock().now(), self._day_night)
        return reply.result_for_actor(view), reply.summary_for_actor(view), time

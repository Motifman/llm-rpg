from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionTaken,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnAction,
    TextWithPeople,
)
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.take_chosen_action import TurnGuidance
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import WorldId


@final
@dataclass(frozen=True)
class DescribeActionTakenCommand:
    reply: ActionReply | TurnGuidance
    call_id: str


@final
@dataclass(frozen=True)
class ActionTakenForActor:
    """``noticed`` は、その行為について本人が知ったことの観測。"""

    taken: ActionTaken
    noticed: Observation | None


@final
class DescribeActionTaken:
    def __init__(
        self, world: WorldId, scope: CommandScope, design: WorldDesign, day_night: DayNightDeclaration
    ) -> None:
        self._world = world
        self._scope = scope
        self._day_night = day_night
        self._clock = design.clock_wording

    def __call__(self, command: DescribeActionTakenCommand) -> ActionTakenForActor:
        # 本文と要約の呼び名と時刻を、同じ時点の世界から作る
        body, summary, time, order = self._scope.run(lambda session: self._read(session, command.reply))
        taken = ActionTaken(
            call_id=command.call_id,
            action_summary=summary,
            accepted=command.reply.succeeded(),
            time=time,
            order=order,
        )
        noticed = Observation(
            body=body,
            route=OwnAction(),
            time=time,
            subject_is_self=True,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=True,
            order=order,
        )
        return ActionTakenForActor(taken=taken, noticed=noticed)

    def _read(
        self, session: WorldSession, reply: ActionReply | TurnGuidance
    ) -> tuple[str | TextWithPeople, TextWithPeople | None, ObservedTime, OccurrenceOrder]:
        view = WorldPerceptionSenses(session.facts()).view_for(reply.actor())
        now = session.clock().now()
        time = self._clock.observed_time_at(now, self._day_night)
        order = OccurrenceOrder(environment=self._world.value, value=now.value)
        return reply.result_for_actor(view), reply.summary_for_actor(view), time, order

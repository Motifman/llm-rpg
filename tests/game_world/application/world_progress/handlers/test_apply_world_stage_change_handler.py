from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.world_progress.apply_world_stage_change import ApplyWorldStageChange
from ai_rpg_world.game_world.application.world_progress.handlers.apply_world_stage_change_handler import (
    ApplyWorldStageChangeHandler,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import Trigger, WorldStageChanged
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb import WorldStageEffectsDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.flag_effects import LowerFlagEffect, RaiseFlagEffect
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId, WorldStageId
from ai_rpg_world.game_world.domain.world_progress import WorldClock, WorldStage, WorldStageChangedEvent
from ai_rpg_world.game_world.domain.world_records import WorldFlagRaisedEvent, WorldFlags
from tests.game_world.application.world_for_handler_tests import NOW, WORLD, WiredWorld
from tests.game_world.support.world_design_for_tests import compose_world, nouns, world_stage

NIGHT = world_stage("night")
DAWN = world_stage("dawn")
LAMPS_OUT = FlagDeclaration(FlagId("lamps_out"), DescriptionText("灯が消された"), initially_raised=False)
ROOSTER = FlagDeclaration(FlagId("rooster_crowed"), DescriptionText("鶏が鳴いた"), initially_raised=False)


class _RaisedBy:
    def __init__(self) -> None:
        self.triggers: list[Trigger] = []

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.triggers += [event.trigger for event in events if isinstance(event, WorldFlagRaisedEvent)]


def _world(*, night_left: Effect, dawn_entered: Effect) -> tuple[WiredWorld, _RaisedBy]:
    design = compose_world(
        nouns(flags=[LAMPS_OUT, ROOSTER], world_stages=[NIGHT, DAWN]),
        world_stage_effects=[
            WorldStageEffectsDeclaration(stage=NIGHT, when_entered=NoEffect(), when_left=night_left),
            WorldStageEffectsDeclaration(stage=DAWN, when_entered=dawn_entered, when_left=NoEffect()),
        ],
        initial_stage=NIGHT,
    )
    world = WiredWorld(
        design, WorldClock.start(WORLD), WorldFlags.start(WORLD), WorldStage.from_initial_stage(WORLD, NIGHT, NOW)
    )
    world.distributor.register_handler(
        WorldStageChangedEvent, ApplyWorldStageChangeHandler(ApplyWorldStageChange(world.scope, design))
    )
    raised_by = _RaisedBy()
    world.distributor.register_receiver(raised_by)
    return world, raised_by


def _dawn_breaks(session: WorldSession) -> None:
    session.aggregates().world_stage().enter(DAWN, NOW)


def _raised(flag: FlagDeclaration) -> Callable[[WorldSession], bool]:
    return lambda session: session.facts().flags().is_raised(flag)


class TestApplyWorldStageChangeHandler:
    """段階が変わったことへの反応で、出る段階と入る段階の効果を当てる挙動を保証する。"""

    def test_effects_of_leaving_and_entering_both_apply(self) -> None:
        """夜から夜明けに変わると、夜を出る効果で灯の旗が立ち、夜明けに入る効果で鶏の旗が立つ。"""
        world, _ = _world(night_left=RaiseFlagEffect(LAMPS_OUT), dawn_entered=RaiseFlagEffect(ROOSTER))

        world.scope.run(_dawn_breaks)

        assert (world.read(_raised(LAMPS_OUT)), world.read(_raised(ROOSTER))) == (True, True)

    def test_entering_effect_applies_after_leaving_effect(self) -> None:
        """夜を出る効果が灯の旗を立て、夜明けに入る効果がそれを下ろすと、夜から夜明けに変わったあと灯の旗は下りている。"""
        world, _ = _world(night_left=RaiseFlagEffect(LAMPS_OUT), dawn_entered=LowerFlagEffect(LAMPS_OUT))

        world.scope.run(_dawn_breaks)

        assert world.read(_raised(LAMPS_OUT)) is False

    def test_effects_receive_the_stage_change_as_trigger(self) -> None:
        """夜から夜明けに変わって立った旗のイベントは、きっかけとして夜から夜明けへの WorldStageChanged を持つ。"""
        world, raised_by = _world(night_left=RaiseFlagEffect(LAMPS_OUT), dawn_entered=NoEffect())

        world.scope.run(_dawn_breaks)

        assert raised_by.triggers == [
            WorldStageChanged(before=WorldStageId("night"), after=WorldStageId("dawn"), at=NOW)
        ]

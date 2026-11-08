from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.domain.condition.condition import FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.happening_conditions import (
    HappeningHasFiredCondition,
    TicksSinceHappeningAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.condition._builders import ALICE, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)


def _happening(happening_id: str) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId(happening_id),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        effect=NoEffect(),
        once=True,
        notice=NoNotice(),
    )


_LANDSLIDE = _happening("landslide")
_EARTHQUAKE = _happening("earthquake")


class TestHappeningHasFiredCondition:
    """HappeningHasFiredCondition が、出来事が一度でも起きたかで真偽を決めることを保証する。"""

    def test_holds_once_the_happening_has_fired(self) -> None:
        """崖崩れがまだ起きていなければ偽、tick 2 に起きたと帳簿に付けたあとは真。"""
        condition = HappeningHasFiredCondition(happening=_LANDSLIDE.happening_id, failure_text=NoText())
        a_world = world()
        assert not condition.holds(a_world.facts(), _BY_ALICE)

        a_world.scenario_progress.note_happening_fired(_LANDSLIDE, WorldTick(2))

        assert condition.holds(a_world.facts(), _BY_ALICE)

    def test_other_happening_firing_does_not_count(self) -> None:
        """地震が起きても、崖崩れの条件は偽のまま。"""
        a_world = world()
        a_world.scenario_progress.note_happening_fired(_EARTHQUAKE, WorldTick(2))

        assert not HappeningHasFiredCondition(happening=_LANDSLIDE.happening_id, failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_failure_carries_its_own_text(self) -> None:
        """まだ起きていないとき、自分の位置と自分の failure_text の文を返す。"""
        condition = HappeningHasFiredCondition(
            happening=_LANDSLIDE.happening_id, failure_text=text("道はまだふさがっていない")
        )

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("道はまだふさがっていない").about({})
        )

    def test_requirements_name_the_happening_it_reads(self) -> None:
        """requirements() は、読む出来事の ID だけを reads_happenings に挙げ、ほかは何も要らない。"""
        assert HappeningHasFiredCondition(happening=_LANDSLIDE.happening_id, failure_text=NoText()).requirements() == (
            replace(Requirements.nothing(), reads_happenings=frozenset({_LANDSLIDE.happening_id}))
        )


def _at_tick(a_world: WorldInMemory, tick: int) -> WorldInMemory:
    while a_world.clock().now() < WorldTick(tick):
        a_world.clock().advance(a_world.day_night)
    return a_world


class TestTicksSinceHappeningAtLeastCondition:
    """TicksSinceHappeningAtLeastCondition が、出来事が最後に起きてから経った tick で真偽を決めることを保証する。"""

    def test_holds_once_enough_ticks_passed_since_the_last_firing(self) -> None:
        """崖崩れが tick 2 に起きたなら、3 tick 以上の条件は tick 4 で偽、tick 5 で真。"""
        condition = TicksSinceHappeningAtLeastCondition(
            happening=_LANDSLIDE.happening_id, ticks=Ticks(3), failure_text=NoText()
        )
        a_world = world()
        a_world.scenario_progress.note_happening_fired(_LANDSLIDE, WorldTick(2))

        assert not condition.holds(_at_tick(a_world, 4).facts(), _BY_ALICE)
        assert condition.holds(_at_tick(a_world, 5).facts(), _BY_ALICE)

    def test_counts_from_the_latest_firing(self) -> None:
        """崖崩れが tick 1 と tick 6 に起きたなら、3 tick 以上の条件は tick 8 で偽。最後に起きた tick 6 から数える。"""
        condition = TicksSinceHappeningAtLeastCondition(
            happening=_LANDSLIDE.happening_id, ticks=Ticks(3), failure_text=NoText()
        )
        a_world = world()
        a_world.scenario_progress.note_happening_fired(_LANDSLIDE, WorldTick(1))
        a_world.scenario_progress.note_happening_fired(_LANDSLIDE, WorldTick(6))

        assert not condition.holds(_at_tick(a_world, 8).facts(), _BY_ALICE)

    def test_never_fired_happening_does_not_hold(self) -> None:
        """一度も起きていない出来事の条件は、0 tick 以上でも、世界が tick 20 まで進んでも偽。"""
        condition = TicksSinceHappeningAtLeastCondition(
            happening=_LANDSLIDE.happening_id, ticks=Ticks(0), failure_text=NoText()
        )

        assert not condition.holds(_at_tick(world(), 20).facts(), _BY_ALICE)

    def test_failure_carries_its_own_text(self) -> None:
        """足りないとき、自分の位置と自分の failure_text の文を返す。"""
        condition = TicksSinceHappeningAtLeastCondition(
            happening=_LANDSLIDE.happening_id, ticks=Ticks(3), failure_text=text("土砂はまだ崩れたばかりだ")
        )

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("土砂はまだ崩れたばかりだ").about({})
        )

    def test_requirements_name_the_happening_it_reads(self) -> None:
        """requirements() は、読む出来事の ID だけを reads_happenings に挙げ、ほかは何も要らない。"""
        condition = TicksSinceHappeningAtLeastCondition(
            happening=_LANDSLIDE.happening_id, ticks=Ticks(3), failure_text=NoText()
        )

        assert condition.requirements() == replace(
            Requirements.nothing(), reads_happenings=frozenset({_LANDSLIDE.happening_id})
        )

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.condition.world_time_conditions import (
    TickAtLeastCondition,
    TickModuloCondition,
    TicksInWorldStageAtLeastCondition,
    TimeOfDayIsCondition,
    WeatherIsCondition,
    WorldStageIsCondition,
)
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.progress import AllActionsAllowed, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    WeatherState,
    WeatherType,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.exception.condition_exception import (
    NotDeclaredInThisWorldException,
    TickModuloOutOfRangeException,
)
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    Probability,
    Ticks,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.world_progress import Weather, WorldStage
from tests.game_world.domain.condition._builders import ALICE, WORLD, text, world
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.world_in_memory import world_in_memory

_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)


def _stage(stage_id: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(stage_id),
        name=DisplayName(stage_id),
        description=DescriptionText(f"{stage_id}の段階"),
        allowed_actions=AllActionsAllowed(),
    )


_DAYTIME = _stage("daytime")
_VOTING = _stage("voting")
_MORNING = DayPhaseName("朝")
_NIGHT = DayPhaseName("夜")
_DAY_NIGHT = DayNightDeclaration(
    ticks_per_day=Ticks(4),
    starts_at=TimeOfDay(0),
    phases=(
        DayPhaseDeclaration(name=_MORNING, begins_at=TimeOfDay(0), dark=False, announcement=NoAnnouncement()),
        DayPhaseDeclaration(name=_NIGHT, begins_at=TimeOfDay(2), dark=True, announcement=NoAnnouncement()),
    ),
)


def _advanced(a_world: WorldSession, ticks: int) -> WorldSession:
    for _ in range(ticks):
        a_world.clock().advance(a_world.facts().day_night())
    return a_world


class TestTickConditions:
    """TickAtLeastCondition と TickModuloCondition が facts.now() で真偽を決めることを保証する。"""

    def test_tick_at_least_holds_from_that_tick(self) -> None:
        """tick 2 以上の条件は、tick 1 で偽、tick 2 で真。"""
        condition = TickAtLeastCondition(tick=WorldTick(2), failure_text=NoText())

        assert not condition.holds(_advanced(world(), 1).facts(), _BY_ALICE)
        assert condition.holds(_advanced(world(), 2).facts(), _BY_ALICE)

    def test_leaf_failure_carries_its_own_text_about_actor(self) -> None:
        """偽の葉は、自分の位置と、自分の failure_text の {actor} に行う人を当てた文を返す。"""
        condition = TickAtLeastCondition(tick=WorldTick(2), failure_text=text("{actor}はまだ待つ"))

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("{actor}はまだ待つ").about({"actor": ALICE})
        )

    def test_leaf_text_placeholder_is_required(self) -> None:
        """葉の failure_text に {target} があれば、葉が主語を見なくても requirements() は TARGET を要る。"""
        condition = TickAtLeastCondition(tick=WorldTick(2), failure_text=text("{target}を待たせている"))

        assert condition.requirements().subjects == frozenset({SubjectKind.TARGET})

    def test_tick_modulo_holds_on_matching_remainder(self) -> None:
        """3 で割って 1 余る tick の条件は、tick 4 で真、tick 5 で偽。"""
        condition = TickModuloCondition(divisor=Ticks(3), remainder=Ticks(1), failure_text=NoText())

        assert condition.holds(_advanced(world(), 4).facts(), _BY_ALICE)
        assert not condition.holds(_advanced(world(), 5).facts(), _BY_ALICE)

    def test_tick_modulo_refuses_zero_divisor(self) -> None:
        """0 で割る TickModuloCondition は作れず、TickModuloOutOfRangeException を投げる。"""
        with pytest.raises(TickModuloOutOfRangeException):
            TickModuloCondition(divisor=Ticks(0), remainder=Ticks(0), failure_text=NoText())

    def test_tick_modulo_refuses_remainder_not_below_divisor(self) -> None:
        """余りが割る数以上の TickModuloCondition は作れず、TickModuloOutOfRangeException を投げる。"""
        with pytest.raises(TickModuloOutOfRangeException):
            TickModuloCondition(divisor=Ticks(3), remainder=Ticks(3), failure_text=NoText())


class TestWorldStageConditions:
    """WorldStageIsCondition と TicksInWorldStageAtLeastCondition が facts.world_stage() を読むことを保証する。"""

    def _world_in(self, stage: WorldStageDeclaration) -> WorldSession:
        return world_in_memory(
            world=WORLD,
            world_stage=WorldStage.from_initial_stage(WORLD, stage, WorldTick(0)),
            stage_declarations=(_DAYTIME, _VOTING),
        )

    def test_current_stage_holds(self) -> None:
        """昼の段階の世界で、昼である条件は真、投票である条件は偽。"""
        facts = self._world_in(_DAYTIME).facts()

        assert WorldStageIsCondition(stage=_DAYTIME, failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not WorldStageIsCondition(stage=_VOTING, failure_text=NoText()).holds(facts, _BY_ALICE)

    def test_ticks_in_stage_count_from_entering(self) -> None:
        """tick 1 に投票へ入った世界は、tick 3 で投票に 2 tick いるので、2 tick 以上は真、3 tick 以上は偽。"""
        a_world = _advanced(self._world_in(_DAYTIME), 1)
        stage = a_world.aggregates().world_stage()
        stage.enter(_VOTING, a_world.facts().now())
        _advanced(a_world, 2)

        assert TicksInWorldStageAtLeastCondition(ticks=Ticks(2), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )
        assert not TicksInWorldStageAtLeastCondition(ticks=Ticks(3), failure_text=NoText()).holds(
            a_world.facts(), _BY_ALICE
        )

    def test_world_without_stages_fails_loudly(self) -> None:
        """段階を宣言しない世界で段階を見ると、NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException):
            WorldStageIsCondition(stage=_DAYTIME, failure_text=NoText()).holds(world().facts(), _BY_ALICE)
        with pytest.raises(NotDeclaredInThisWorldException):
            TicksInWorldStageAtLeastCondition(ticks=Ticks(0), failure_text=NoText()).holds(world().facts(), _BY_ALICE)


class TestTimeOfDayIs:
    """TimeOfDayIsCondition が facts.clock() と facts.day_night() で今の時間帯を決めることを保証する。"""

    def test_phase_follows_the_clock(self) -> None:
        """朝が 0、夜が 2 から始まる 1 日 4 tick の世界で、tick 1 は朝、tick 2 は夜。"""
        morning = TimeOfDayIsCondition(phase=_MORNING, failure_text=NoText())
        night = TimeOfDayIsCondition(phase=_NIGHT, failure_text=NoText())

        tick_one = _advanced(world_in_memory(world=WORLD, day_night=_DAY_NIGHT), 1).facts()
        tick_two = _advanced(world_in_memory(world=WORLD, day_night=_DAY_NIGHT), 2).facts()

        assert morning.holds(tick_one, _BY_ALICE) and not night.holds(tick_one, _BY_ALICE)
        assert night.holds(tick_two, _BY_ALICE) and not morning.holds(tick_two, _BY_ALICE)

    def test_world_without_day_night_fails_loudly(self) -> None:
        """昼夜を宣言しない世界で時間帯を見ると、NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException):
            TimeOfDayIsCondition(phase=_MORNING, failure_text=NoText()).holds(world().facts(), _BY_ALICE)


class TestWeatherIs:
    """WeatherIsCondition が facts.weather() の今の天候を見ることを保証する。"""

    def test_current_weather_holds(self) -> None:
        """雨の世界で、雨である条件は真、晴れである条件は偽。"""
        facts = world_in_memory(world=WORLD, weather=Weather(WORLD, WeatherState(WeatherType.RAIN))).facts()

        assert WeatherIsCondition(weather=WeatherType.RAIN, failure_text=NoText()).holds(facts, _BY_ALICE)
        assert not WeatherIsCondition(weather=WeatherType.CLEAR, failure_text=NoText()).holds(facts, _BY_ALICE)

    def test_world_without_weather_fails_loudly(self) -> None:
        """天候を宣言しない世界で天候を見ると、NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException):
            WeatherIsCondition(weather=WeatherType.RAIN, failure_text=NoText()).holds(world().facts(), _BY_ALICE)


class TestChance:
    """ChanceCondition が facts.random() から 1 つ引き、確率より小さければ真になることを保証する。"""

    def test_fraction_below_probability_holds(self) -> None:
        """確率 0.3 の条件は、0.29 を引けば真、0.3 を引けば偽。"""
        condition = ChanceCondition(probability=Probability(0.3), failure_text=NoText())

        assert condition.holds(world(fractions=(0.29,)).facts(), _BY_ALICE)
        assert not condition.holds(world(fractions=(0.3,)).facts(), _BY_ALICE)

    def test_requires_chance(self) -> None:
        """ChanceCondition の requirements() は uses_chance が真。"""
        assert ChanceCondition(probability=Probability(0.3), failure_text=NoText()).requirements().uses_chance


class TestWhatWorldTimeConditionsRead:
    """段階・昼夜・天候を見る条件が、何を読むかを requirements() で答えることを保証する。"""

    def test_world_stage_conditions_read_the_world_stage(self) -> None:
        """WorldStageIs と TicksInWorldStageAtLeast は段階を読み、昼夜と天候は読まない。"""
        for condition in (
            WorldStageIsCondition(stage=_DAYTIME, failure_text=NoText()),
            TicksInWorldStageAtLeastCondition(ticks=Ticks(2), failure_text=NoText()),
        ):
            requirements = condition.requirements()
            assert requirements.reads_world_stage
            assert requirements.reads_day_phases == frozenset()
            assert not requirements.reads_weather

    def test_time_of_day_reads_its_day_phase(self) -> None:
        """TimeOfDayIs(夜) は昼夜の段階「夜」を読み、段階は読まない。"""
        requirements = TimeOfDayIsCondition(phase=_NIGHT, failure_text=NoText()).requirements()

        assert requirements.reads_day_phases == frozenset({_NIGHT})
        assert not requirements.reads_world_stage

    def test_weather_is_reads_the_weather(self) -> None:
        """WeatherIs は天候を読む。"""
        assert WeatherIsCondition(weather=WeatherType.FOG, failure_text=NoText()).requirements().reads_weather

    def test_tick_conditions_read_none_of_them(self) -> None:
        """TickAtLeast は段階も昼夜も天候も読まない。"""
        requirements = TickAtLeastCondition(tick=WorldTick(3), failure_text=NoText()).requirements()

        assert not requirements.reads_world_stage
        assert requirements.reads_day_phases == frozenset()
        assert not requirements.reads_weather

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ChangesEvery,
    NoChange,
    WeatherDeclaration,
    WeatherState,
    WeatherTransitionRow,
    WeatherTransitions,
    WeatherType,
    WeightedWeather,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.time_and_weather_exception import (
    NoNextWeatherDeclaredException,
    WeatherTransitionDuplicatedException,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, Probability, Ticks


def _transitions(*rows: WeatherTransitionRow) -> WeatherTransitions:
    return WeatherTransitions(rows=rows)


def _row(current: WeatherType, *weighted: tuple[WeatherType, int]) -> WeatherTransitionRow:
    return WeatherTransitionRow(
        current=current, candidates=tuple(WeightedWeather(weather=w, weight=n) for w, n in weighted)
    )


def _declaration(changes: NoChange | ChangesEvery) -> WeatherDeclaration:
    return WeatherDeclaration(
        initial=WeatherType.CLEAR,
        changes=changes,
        announce_changes=True,
        obscuring=frozenset({WeatherType.FOG, WeatherType.STORM}),
    )


class TestWeightedWeather:
    """WeightedWeather が、次の天候の重みとして 1 以上の整数だけを受けることを保証する。"""

    def test_rejects_zero_weight(self) -> None:
        """重み 0 は ValueOutOfRangeException で断る。"""
        with pytest.raises(ValueOutOfRangeException):
            WeightedWeather(weather=WeatherType.RAIN, weight=0)


class TestWeatherTransitionsValidation:
    """WeatherTransitions が、次の天候を 1 つに決められない表を作るときに断ることを保証する。"""

    def test_rejects_row_without_candidates(self) -> None:
        """次の天候が 1 つも無い行は NoNextWeatherDeclaredException で断る。"""
        with pytest.raises(NoNextWeatherDeclaredException):
            _row(WeatherType.CLEAR)

    def test_rejects_same_candidate_twice_in_a_row(self) -> None:
        """1 つの行に同じ次の天候が 2 回出ると WeatherTransitionDuplicatedException で断る。"""
        with pytest.raises(WeatherTransitionDuplicatedException):
            _row(WeatherType.CLEAR, (WeatherType.RAIN, 1), (WeatherType.RAIN, 2))

    def test_rejects_two_rows_for_same_weather(self) -> None:
        """同じ今の天候の行が 2 つあると WeatherTransitionDuplicatedException で断る。"""
        with pytest.raises(WeatherTransitionDuplicatedException):
            _transitions(
                _row(WeatherType.CLEAR, (WeatherType.RAIN, 1)),
                _row(WeatherType.CLEAR, (WeatherType.FOG, 1)),
            )


class TestWeatherTransitionsNextAfter:
    """WeatherTransitions.next_after が、今の天候の行の重みに沿って roll から次の天候を選ぶことを保証する。"""

    def test_low_roll_picks_first_candidate(self) -> None:
        """晴れ 3・雨 1 の行で roll 0.0 は晴れを選ぶ。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.CLEAR, 3), (WeatherType.RAIN, 1)))

        assert table.next_after(WeatherType.CLEAR, Probability(0.0)) == WeatherType.CLEAR

    def test_roll_past_cumulative_weight_picks_next_candidate(self) -> None:
        """晴れ 3・雨 1 の行で、晴れの割合 0.75 ちょうどの roll は雨を選ぶ。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.CLEAR, 3), (WeatherType.RAIN, 1)))

        assert table.next_after(WeatherType.CLEAR, Probability(0.75)) == WeatherType.RAIN

    def test_roll_just_below_cumulative_weight_stays_in_candidate(self) -> None:
        """晴れ 3・雨 1 の行で roll 0.74 は晴れを選ぶ。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.CLEAR, 3), (WeatherType.RAIN, 1)))

        assert table.next_after(WeatherType.CLEAR, Probability(0.74)) == WeatherType.CLEAR

    def test_roll_of_one_picks_last_candidate(self) -> None:
        """roll 1.0 は行の最後の天候を選ぶ。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.CLEAR, 3), (WeatherType.RAIN, 1)))

        assert table.next_after(WeatherType.CLEAR, Probability(1.0)) == WeatherType.RAIN

    def test_weather_without_row_stays_unchanged(self) -> None:
        """表に行の無い天候は、roll によらず変わらない。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.RAIN, 1)))

        assert table.next_after(WeatherType.SNOW, Probability(0.5)) == WeatherType.SNOW


class TestDefaultWeatherTransitions:
    """WeatherTransitions.default が、作者が表を書かなかったときの既定の表を返すことを保証する。"""

    def test_every_weather_type_has_a_row(self) -> None:
        """既定の表は、8 種の天候すべてに行を持つ。"""
        table = WeatherTransitions.default()

        assert {row.current for row in table.rows} == set(WeatherType)

    def test_clear_weather_never_turns_into_storm_directly(self) -> None:
        """既定の表では、晴れから次に選ばれうるのは晴れ・曇り・霧だけで、嵐にはならない。"""
        table = WeatherTransitions.default()

        reachable = {table.next_after(WeatherType.CLEAR, Probability(r / 100)) for r in range(101)}

        assert reachable == {WeatherType.CLEAR, WeatherType.CLOUDY, WeatherType.FOG}


class TestChangesEvery:
    """ChangesEvery が、天候を変える間隔として 1 tick 以上だけを受けることを保証する。"""

    def test_rejects_zero_ticks(self) -> None:
        """間隔 0 tick は ValueOutOfRangeException で断る。"""
        with pytest.raises(ValueOutOfRangeException):
            ChangesEvery(ticks=Ticks(0), transitions=WeatherTransitions.default())


class TestWeatherDeclarationNextAfter:
    """WeatherDeclaration.next_after が、変わり方の宣言に沿って次の天候を返すことを保証する。"""

    def test_no_change_keeps_current_weather(self) -> None:
        """NoChange の天候は、roll によらず今の天候のまま。"""
        declaration = _declaration(NoChange())

        assert declaration.next_after(WeatherState(WeatherType.FOG), Probability(0.9)) == WeatherState(WeatherType.FOG)

    def test_changes_every_follows_transitions(self) -> None:
        """ChangesEvery の天候は、その表で次の天候を選ぶ。"""
        table = _transitions(_row(WeatherType.CLEAR, (WeatherType.RAIN, 1)))
        declaration = _declaration(ChangesEvery(ticks=Ticks(5), transitions=table))

        assert declaration.next_after(WeatherState(WeatherType.CLEAR), Probability(0.3)) == WeatherState(
            WeatherType.RAIN
        )


class TestWeatherDeclarationObscuresSight:
    """WeatherDeclaration.obscures_sight が、宣言した見通しの悪い天候でだけ真になることを保証する。"""

    def test_declared_obscuring_weather_obscures_sight(self) -> None:
        """obscuring に霧を含む宣言で、霧は見通しを悪くする。"""
        assert _declaration(NoChange()).obscures_sight(WeatherState(WeatherType.FOG)) is True

    def test_other_weather_does_not_obscure_sight(self) -> None:
        """obscuring に含まれない雨は、見通しを悪くしない。"""
        assert _declaration(NoChange()).obscures_sight(WeatherState(WeatherType.RAIN)) is False


class TestWeatherDeclarationDisplayName:
    """WeatherDeclaration.display_name が、天候の種類を文に出す日本語の呼び名にすることを保証する。"""

    @pytest.mark.parametrize(
        ("weather", "name"),
        [
            (WeatherType.CLEAR, "晴れ"),
            (WeatherType.CLOUDY, "曇り"),
            (WeatherType.RAIN, "雨"),
            (WeatherType.HEAVY_RAIN, "豪雨"),
            (WeatherType.SNOW, "雪"),
            (WeatherType.BLIZZARD, "吹雪"),
            (WeatherType.FOG, "霧"),
            (WeatherType.STORM, "嵐"),
        ],
    )
    def test_names_each_weather_type(self, weather: WeatherType, name: str) -> None:
        """8 種の天候それぞれに、決まった日本語の呼び名を返す。"""
        assert _declaration(NoChange()).display_name(WeatherState(weather)) == DisplayName(name)

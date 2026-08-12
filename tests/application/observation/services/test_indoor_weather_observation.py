"""屋内スポットでの天候観測抑制テスト。

DefaultRecipientStrategy が SpotWeatherChangedEvent を処理する際、
スポットが is_outdoor=False（屋内）なら、たとえそのスポットにプレイヤーが
いても観測配信先から除外されることを検証する。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.default_recipient_strategy import (
    DefaultRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.event.map_events import SpotWeatherChangedEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _build_graph_with_spot(spot_id_value: int, *, is_outdoor: bool) -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SpotId.create(spot_id_value),
            name=f"spot_{spot_id_value}",
            description="",
            category=SpotCategoryEnum.TOWN,
            parent_id=None,
            is_outdoor=is_outdoor,
        )
    )
    graph.clear_events()
    return graph


def _make_strategy(graph: SpotGraphAggregate, audience_player_ids: list[int]):
    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph

    audience_query = MagicMock()
    audience_query.players_at_spot.return_value = [PlayerId(pid) for pid in audience_player_ids]

    world_object_resolver = MagicMock()

    return DefaultRecipientStrategy(
        observed_event_registry=ObservedEventRegistry(),
        player_audience_query=audience_query,
        world_object_to_player_resolver=world_object_resolver,
        spot_graph_repository=spot_graph_repo,
    )


def _weather_event(spot_id_value: int) -> SpotWeatherChangedEvent:
    return SpotWeatherChangedEvent.create(
        aggregate_id=SpotId.create(spot_id_value),
        aggregate_type="Weather",
        spot_id=SpotId.create(spot_id_value),
        old_weather_state=WeatherState.clear(),
        new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
    )


class TestSpotWeatherObservationByIsOutdoor:
    def test_outdoor_spot_delivers_to_players_at_spot(self):
        """屋外スポット: そのスポットにいるプレイヤーが配信先になる"""
        graph = _build_graph_with_spot(1, is_outdoor=True)
        strategy = _make_strategy(graph, audience_player_ids=[1, 2])

        result = strategy.resolve(_weather_event(1))

        assert {p.value for p in result} == {1, 2}

    def test_indoor_spot_suppresses_delivery_even_with_players(self):
        """屋内スポット: プレイヤーがいても観測フィードに天候変化を流さない"""
        graph = _build_graph_with_spot(1, is_outdoor=False)
        strategy = _make_strategy(graph, audience_player_ids=[1, 2])

        result = strategy.resolve(_weather_event(1))

        assert result == []

    def test_unknown_spot_in_graph_falls_back_to_audience(self):
        """SpotGraph に登録されていないスポットでは抑制せず従来挙動を維持する"""
        graph = _build_graph_with_spot(99, is_outdoor=True)
        strategy = _make_strategy(graph, audience_player_ids=[7])

        result = strategy.resolve(_weather_event(1))

        assert [p.value for p in result] == [7]

    def test_no_repository_falls_back_to_audience(self):
        """SpotGraph リポジトリ未注入の場合は従来挙動（抑制なし）"""
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = [PlayerId(3)]
        strategy = DefaultRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            world_object_to_player_resolver=MagicMock(),
        )

        result = strategy.resolve(_weather_event(1))

        assert [p.value for p in result] == [3]


class TestTheIndoorCheckFailingIsVisible:
    """屋内判定が壊れたことが、静かに消えずに見える。

    ## なぜこの試験が要るか

    判定は丸ごと ``except Exception: pass`` で囲まれていた。``find_graph`` /
    ``contains_spot`` / ``get_spot`` のどこで落ちても抑制の ``return`` に到達せず、
    **屋内にいる人へ屋外の天候が届く**。しかも trace にも log にも何も残らないので、
    **発火していないのか、発火して静かなのかを区別できない**。

    ## 規模

    ``is_outdoor`` の既定値は ``False`` (= 屋内) である。実測すると

        abandoned_hospital     全 16 spot 中 15 が屋内扱い / 天候 有効
        survival_island_v4     全 25 spot 中  5 が屋内扱い / 天候 有効

    で、実 run の天候観測は 524 件ある。発火すれば大量の誤配信になる。

    ## 既存試験が例外経路を 1 件も通していなかった

    上の 4 件はすべて正常系である。「屋内なら配らない」は今のコードでも通るので、
    **正の対照だけでは握り潰しを検出できない**。リポジトリを例外を投げるスタブへ
    差し替えて初めて分かる。
    """

    def _strategy_with_failing_repository(self, exc: Exception):
        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.side_effect = exc
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = [PlayerId(1), PlayerId(2)]
        return DefaultRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            world_object_to_player_resolver=MagicMock(),
            spot_graph_repository=spot_graph_repo,
        )

    def test_a_failing_repository_raises_instead_of_delivering(self) -> None:
        """判定に失敗したら、黙って全員へ配らずに例外を投げる。

        以前は「従来挙動を維持」として**全員に配って**いた。既定が屋内なので、
        その「従来挙動」は屋内主体のシナリオでほぼ全スポットに誤配信する。

        上流 (`ObservationRecipientResolver.resolve` / `ObservationPipeline`) に
        広い ``except`` は無いことを確認済みなので、投げれば実際に見える。
        """
        strategy = self._strategy_with_failing_repository(RuntimeError("repo down"))

        with pytest.raises(RuntimeError):
            strategy.resolve(_weather_event(1))

    def test_the_failure_is_logged_with_the_spot(self, caplog) -> None:
        """落ちたことと対象スポットが warning に残る。

        投げるだけだと上流の trace には出るが、**どのスポットの判定で落ちたか**が
        分からない。原因究明に要る情報を落とさない。
        """
        strategy = self._strategy_with_failing_repository(RuntimeError("repo down"))

        with caplog.at_level(logging.WARNING):
            with pytest.raises(RuntimeError):
                strategy.resolve(_weather_event(1))

        messages = [r.getMessage() for r in caplog.records]
        assert any("1" in m for m in messages), messages

    def test_an_unregistered_spot_still_falls_back(self) -> None:
        """例外ではない「登録されていない」は従来どおり全員へ配る (正の対照)。

        ``contains_spot`` が False のときの分岐は**例外とは別の正当な判断**である。
        2 つを混ぜると、片方を直したときにもう片方が壊れる。この試験があるので
        「例外も未登録も全部投げる」実装では通らない。
        """
        graph = _build_graph_with_spot(99, is_outdoor=True)
        strategy = _make_strategy(graph, audience_player_ids=[7])

        result = strategy.resolve(_weather_event(1))

        assert [p.value for p in result] == [7]

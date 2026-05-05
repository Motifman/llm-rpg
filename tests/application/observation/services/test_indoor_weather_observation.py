"""屋内スポットでの天候観測抑制テスト。

DefaultRecipientStrategy が SpotWeatherChangedEvent を処理する際、
スポットが is_outdoor=False（屋内）なら、たとえそのスポットにプレイヤーが
いても観測配信先から除外されることを検証する。
"""

from __future__ import annotations

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

"""ObservationFormatter のテスト（プローズ・構造化の両方・未知イベント）"""

import pytest

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    SpotWeatherChangedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats


class TestObservationFormatter:
    """ObservationFormatter の正常・境界・未知イベント"""

    @pytest.fixture
    def formatter(self):
        """リポジトリなし（フォールバック名のみ）"""
        return ObservationFormatter(spot_repository=None, player_profile_repository=None)

    def test_format_gateway_triggered_self_returns_prose_and_structured(self, formatter):
        """GatewayTriggeredEvent 本人向け: プローズと構造化の両方"""
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "到着" in out.prose
        assert out.structured.get("type") == "gateway_arrival"
        assert "spot_name" in out.structured

    def test_format_gateway_triggered_other_returns_entered_message(self, formatter):
        """GatewayTriggeredEvent 他プレイヤー向け: 誰かがやってきた"""
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "やってきました" in out.prose
        assert out.structured.get("type") == "player_entered_spot"

    def test_format_player_level_up_returns_prose_and_structured(self, formatter):
        """PlayerLevelUpEvent: レベルアップ文と構造化"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "1" in out.prose and "2" in out.prose
        assert out.structured.get("old_level") == 1
        assert out.structured.get("new_level") == 2

    def test_format_player_gold_earned_returns_amount_in_prose(self, formatter):
        """PlayerGoldEarnedEvent: 獲得金額がプローズに含まれる"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=50,
            total_gold=1050,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "50" in out.prose
        assert out.structured.get("amount") == 50

    def test_format_player_gold_paid_returns_amount(self, formatter):
        """PlayerGoldPaidEvent: 支払い金額"""
        event = PlayerGoldPaidEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            paid_amount=30,
            total_gold=970,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "30" in out.prose

    def test_format_spot_weather_changed_returns_old_new_in_prose(self, formatter):
        """SpotWeatherChangedEvent: 天気変化のプローズと構造化"""
        event = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Weather",
            spot_id=SpotId(1),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "天気" in out.prose
        assert out.structured.get("type") == "weather_changed"

    def test_format_unknown_event_returns_none(self, formatter):
        """未知のイベントは None"""
        class UnknownEvent:
            pass
        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

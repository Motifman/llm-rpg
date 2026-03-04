"""ObservationFormatter のテスト（プローズ・構造化・未知イベント・リポジトリ有無・フォールバック）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
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
    PlayerDownedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
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
        assert out.causes_interrupt is True

    def test_format_gateway_triggered_self_does_not_cause_interrupt(self, formatter):
        """GatewayTriggeredEvent 本人向けは causes_interrupt=False（到着は割り込み不要）"""
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
        assert out.causes_interrupt is False

    def test_format_player_downed_self_causes_interrupt(self, formatter):
        """PlayerDownedEvent 本人向けは causes_interrupt=True（ダメージで割り込み）"""
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "戦闘不能" in out.prose
        assert out.causes_interrupt is True

    def test_format_item_added_to_inventory_causes_interrupt(self, formatter):
        """ItemAddedToInventoryEvent 本人向けは causes_interrupt=True（アイテム発見で割り込み）"""
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "入手" in out.prose
        assert out.causes_interrupt is True

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

    # --- スポット名・プレイヤー名のリポジトリ有無・フォールバック ---

    def test_format_spot_name_returns_fallback_when_repository_none(self, formatter):
        """spot_repository が None のとき、スポット名は「スポット{id}」のフォールバックになる"""
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
        assert out.structured.get("spot_name") == "スポット2"
        assert "スポット2" in out.prose

    def test_format_spot_name_uses_repository_when_available(self):
        """spot_repository でスポットが取得できるとき、その名前が観測に含まれる"""
        spot_repo = MagicMock()
        spot = MagicMock()
        spot.name = "町の広場"
        spot_repo.find_by_id.return_value = spot
        formatter = ObservationFormatter(
            spot_repository=spot_repo,
            player_profile_repository=None,
        )
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
        assert out.structured.get("spot_name") == "町の広場"
        assert "町の広場" in out.prose

    def test_format_spot_name_returns_fallback_when_repository_returns_none(self):
        """spot_repository が設定されていても find_by_id が None を返すときはフォールバック名"""
        spot_repo = MagicMock()
        spot_repo.find_by_id.return_value = None
        formatter = ObservationFormatter(
            spot_repository=spot_repo,
            player_profile_repository=None,
        )
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
        assert out.structured.get("spot_name") == "スポット2"

    def test_format_player_name_returns_fallback_when_repository_none(self, formatter):
        """player_profile_repository が None のとき、他プレイヤー名は「プレイヤー{id}」のフォールバックになる"""
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
        assert out.structured.get("actor") == "プレイヤー1"
        assert "プレイヤー1" in out.prose

    def test_format_player_name_uses_repository_when_available(self):
        """player_profile_repository でプロフィールが取得できるとき、その名前が観測に含まれる"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=profile_repo,
        )
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
        assert out.structured.get("actor") == "Alice"
        assert "Alice" in out.prose

    def test_format_player_name_returns_fallback_when_repository_returns_none(self):
        """player_profile_repository が設定されていても find_by_id が None を返すときはフォールバック名"""
        profile_repo = MagicMock()
        profile_repo.find_by_id.return_value = None
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=profile_repo,
        )
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
        assert out.structured.get("actor") == "プレイヤー1"

    # --- attention_level によるフィルタ（FULL / FILTER_SOCIAL / IGNORE）---

    def test_format_with_full_or_none_returns_all_categories(self, formatter):
        """attention_level が FULL または None のときは全カテゴリをそのまま返す（正常系）"""
        # 本人向け（self_only）
        event_self = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out_full = formatter.format(event_self, PlayerId(1), attention_level=AttentionLevel.FULL)
        out_none = formatter.format(event_self, PlayerId(1), attention_level=None)
        assert out_full is not None and out_full.observation_category == "self_only"
        assert out_none is not None and out_none.observation_category == "self_only"

        # 他者向け（social）
        event_gateway = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        out_social = formatter.format(event_gateway, PlayerId(2), attention_level=AttentionLevel.FULL)
        assert out_social is not None and out_social.observation_category == "social"

        # 環境（environment）
        event_weather = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Weather",
            spot_id=SpotId(1),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        out_env = formatter.format(event_weather, PlayerId(1), attention_level=AttentionLevel.FULL)
        assert out_env is not None and out_env.observation_category == "environment"

    def test_format_with_filter_social_skips_social_category(self, formatter):
        """FILTER_SOCIAL のとき social カテゴリは None（スキップ）、self_only は返る（正常系）"""
        # 他者向け（social）→ スキップ
        event_gateway = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        out = formatter.format(event_gateway, PlayerId(2), attention_level=AttentionLevel.FILTER_SOCIAL)
        assert out is None

        # 本人向け（self_only）→ 返る
        event_level = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out_self = formatter.format(event_level, PlayerId(1), attention_level=AttentionLevel.FILTER_SOCIAL)
        assert out_self is not None
        assert out_self.observation_category == "self_only"

    def test_format_with_filter_social_returns_environment(self, formatter):
        """FILTER_SOCIAL のとき environment カテゴリはそのまま返す"""
        event_weather = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Weather",
            spot_id=SpotId(1),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        out = formatter.format(event_weather, PlayerId(1), attention_level=AttentionLevel.FILTER_SOCIAL)
        assert out is not None
        assert out.observation_category == "environment"

    def test_format_with_ignore_returns_only_self_only(self, formatter):
        """IGNORE のとき self_only のみ返し、social / environment は None（正常系）"""
        # self_only → 返る
        event_level = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out_self = formatter.format(event_level, PlayerId(1), attention_level=AttentionLevel.IGNORE)
        assert out_self is not None
        assert out_self.observation_category == "self_only"

        # social → None
        event_gateway = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        out_social = formatter.format(event_gateway, PlayerId(2), attention_level=AttentionLevel.IGNORE)
        assert out_social is None

        # environment → None
        event_weather = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Weather",
            spot_id=SpotId(1),
            old_weather_state=WeatherState.clear(),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.5),
        )
        out_env = formatter.format(event_weather, PlayerId(1), attention_level=AttentionLevel.IGNORE)
        assert out_env is None

    def test_format_event_none_returns_none(self, formatter):
        """event が None のときは None を返す（未知イベント扱い）"""
        out = formatter.format(None, PlayerId(1))  # type: ignore[arg-type]
        assert out is None

    def test_format_unknown_attention_level_treated_as_full_returns_output(self, formatter):
        """attention_level が enum 外の値のときはフィルタされず output がそのまま返る（実装の境界）"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        # enum 以外の値を渡す（型チェックでは Optional[AttentionLevel] のため type: ignore 使用）
        out = formatter.format(event, PlayerId(1), attention_level="invalid")  # type: ignore[arg-type]
        assert out is not None
        assert out.observation_category == "self_only"

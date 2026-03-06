"""ObservationFormatter のテスト（プローズ・構造化・未知イベント・リポジトリ有無・フォールバック）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    ItemStoredInChestEvent,
    ItemTakenFromChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
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
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
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
        """spot_repository が None のとき、スポット名は「不明なスポット」になる（ID非露出）"""
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
        assert out.structured.get("spot_name") == "不明なスポット"
        assert "不明なスポット" in out.prose
        assert "スポット2" not in out.prose  # ID 非露出

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
        """spot_repository が設定されていても find_by_id が None を返すときは「不明なスポット」"""
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
        assert out.structured.get("spot_name") == "不明なスポット"

    def test_format_player_name_returns_fallback_when_repository_none(self, formatter):
        """player_profile_repository が None のとき、他プレイヤー名は「不明なプレイヤー」になる（ID非露出）"""
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
        assert out.structured.get("actor") == "不明なプレイヤー"
        assert "不明なプレイヤー" in out.prose
        assert "プレイヤー1" not in out.prose  # ID が露出していないこと

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
        """player_profile_repository が設定されていても find_by_id が None を返すときは「不明なプレイヤー」"""
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
        assert out.structured.get("actor") == "不明なプレイヤー"

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

    # --- ResourceHarvestedEvent / WorldObjectInteracted / アイテム名フォールバック ---

    def test_format_resource_harvested_empty_items_returns_prose(self, formatter):
        """ResourceHarvestedEvent: obtained_items が空のとき「採集しました。」"""
        event = ResourceHarvestedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            object_id=WorldObjectId(1),
            actor_id=WorldObjectId(2),
            loot_table_id=LootTableId.create(1),
            obtained_items=[],
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "採集" in out.prose
        assert out.structured.get("type") == "resource_harvested"

    def test_format_resource_harvested_with_items_uses_fallback_without_repo(self, formatter):
        """ResourceHarvestedEvent: item_spec_repository なしのとき「何かのアイテム」で表示"""
        event = ResourceHarvestedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            object_id=WorldObjectId(1),
            actor_id=WorldObjectId(2),
            loot_table_id=LootTableId.create(1),
            obtained_items=[{"item_spec_id": 10, "quantity": 2}],
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "2" in out.prose
        assert "10" not in out.prose  # ID 非露出

    def test_format_resource_harvested_with_item_spec_repository_resolves_name(self):
        """ResourceHarvestedEvent: item_spec_repository で名前解決できるときアイテム名を表示"""
        spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "銅の鉱石"
        spec_repo.find_by_id.return_value = spec
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=None,
            item_spec_repository=spec_repo,
            item_repository=None,
        )
        event = ResourceHarvestedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            object_id=WorldObjectId(1),
            actor_id=WorldObjectId(2),
            loot_table_id=LootTableId.create(1),
            obtained_items=[{"item_spec_id": 10, "quantity": 2}],
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "銅の鉱石" in out.prose
        assert "2" in out.prose

    def test_format_world_object_interacted_open_chest_returns_5w1h_prose(self, formatter):
        """WorldObjectInteractedEvent OPEN_CHEST: 「宝箱を開けました。」（5W1H）"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.OPEN_CHEST,
            data={},
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "宝箱を開けました" in out.prose
        assert "インタラクション" not in out.prose

    def test_format_world_object_interacted_open_door_uses_data(self, formatter):
        """WorldObjectInteractedEvent OPEN_DOOR: data.is_open で開く/閉めるを切り替え"""
        event_open = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.OPEN_DOOR,
            data={"is_open": True},
        )
        out_open = formatter.format(event_open, PlayerId(2))
        assert out_open is not None
        assert "ドアを開きました" in out_open.prose
        event_close = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.OPEN_DOOR,
            data={"is_open": False},
        )
        out_close = formatter.format(event_close, PlayerId(2))
        assert out_close is not None
        assert "ドアを閉めました" in out_close.prose

    def test_format_world_object_interacted_harvest_returns_prose(self, formatter):
        """WorldObjectInteractedEvent HARVEST: 「資源を採取しました。」"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.HARVEST,
            data={},
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "資源を採取しました" in out.prose

    def test_format_item_taken_from_chest_fallback_without_repo(self, formatter):
        """ItemTakenFromChestEvent: item_repository なしのとき「何かのアイテム」"""
        event = ItemTakenFromChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Chest",
            spot_id=SpotId(1),
            chest_id=WorldObjectId(1),
            actor_id=WorldObjectId(2),
            item_instance_id=ItemInstanceId.create(100),
            player_id_value=2,
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "チェストから" in out.prose
        assert "100" not in out.prose

    def test_format_item_taken_from_chest_resolves_name_when_repo_available(self):
        """ItemTakenFromChestEvent: item_repository で名前解決できるときアイテム名を表示"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        item_repo.find_by_id.return_value = agg
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=None,
            item_spec_repository=None,
            item_repository=item_repo,
        )
        event = ItemTakenFromChestEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Chest",
            spot_id=SpotId(1),
            chest_id=WorldObjectId(1),
            actor_id=WorldObjectId(2),
            item_instance_id=ItemInstanceId.create(100),
            player_id_value=2,
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "銅の剣" in out.prose
        assert out.structured.get("item_name") == "銅の剣"

    def test_format_item_added_to_inventory_fallback_without_repo(self, formatter):
        """ItemAddedToInventoryEvent: item_repository なしのとき「何かのアイテムを入手」"""
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "入手" in out.prose

    def test_format_item_dropped_fallback_without_repo(self, formatter):
        """ItemDroppedFromInventoryEvent: リポジトリなしのとき「何かのアイテムを捨てました」"""
        event = ItemDroppedFromInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
            slot_id=SlotId(0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "捨て" in out.prose

    def test_format_item_equipped_and_unequipped_fallback(self, formatter):
        """ItemEquippedEvent / ItemUnequippedEvent: リポジトリなしのときフォールバック"""
        event_equip = ItemEquippedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
            from_slot_id=SlotId(0),
            to_equipment_slot=EquipmentSlotType.WEAPON,
        )
        out_equip = formatter.format(event_equip, PlayerId(1))
        assert out_equip is not None
        assert "何かのアイテム" in out_equip.prose
        assert "装備" in out_equip.prose
        event_unequip = ItemUnequippedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
            from_equipment_slot=EquipmentSlotType.WEAPON,
            to_slot_id=SlotId(0),
        )
        out_unequip = formatter.format(event_unequip, PlayerId(1))
        assert out_unequip is not None
        assert "何かのアイテム" in out_unequip.prose
        assert "外しました" in out_unequip.prose

    def test_format_inventory_slot_overflow_fallback(self, formatter):
        """InventorySlotOverflowEvent: リポジトリなしのとき「何かのアイテムが溢れました」"""
        event = InventorySlotOverflowEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            overflowed_item_instance_id=ItemInstanceId.create(1),
            reason="equip_replacement",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "溢れ" in out.prose

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

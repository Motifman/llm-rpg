"""WorldObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.world_formatter import (
    WorldObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    ItemStoredInChestEvent,
    ItemTakenFromChestEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.skill.event.skill_events import SkillEquippedEvent
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


def _make_context(
    player_profile_repository=None,
    item_spec_repository=None,
    item_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=player_profile_repository,
        item_spec_repository=item_spec_repository,
        item_repository=item_repository,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=item_repository,
    )


class TestWorldObservationFormatterCreation:
    """WorldObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestWorldObservationFormatterLocationEntered:
    """LocationEnteredEvent のフォーマットテスト"""

    def test_self_with_description_includes_description(self):
        """本人向け・description あり: prose に description が含まれる。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationEnteredEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            name="町の広場",
            description="賑やかな市場が並ぶ中央広場。",
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "町の広場に着きました。" in out.prose
        assert "賑やかな市場が並ぶ中央広場。" in out.prose
        assert out.structured.get("type") == "location_entered"
        assert out.observation_category == "self_only"

    def test_self_without_description_returns_arrival_only(self):
        """本人向け・description なし: prose は「〜に着きました。」のみ。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationEnteredEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            name="空き地",
            description="",
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.prose == "空き地に着きました。"

    def test_other_player_uses_player_repository(self):
        """他プレイヤー向け: player_profile_repository で名前解決。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationEnteredEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(2),
            name="秘密の部屋",
            description="誰も知らない隠し場所。",
            player_id_value=2,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bobが秘密の部屋に着きました。" in out.prose
        assert out.structured.get("type") == "player_entered_location"
        assert out.observation_category == "social"

    def test_player_id_none_uses_fallback(self):
        """player_id_value が None のときフォールバック名。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationEnteredEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            name="入口",
            description="",
            player_id_value=None,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "不明なプレイヤー" in out.prose


class TestWorldObservationFormatterLocationExited:
    """LocationExitedEvent のフォーマットテスト"""

    def test_returns_exited_prose(self):
        """退出は prose と schedules_turn を返す。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationExitedEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "ロケーションを出ました" in out.prose
        assert out.structured.get("type") == "location_exited"
        assert out.schedules_turn is True


class TestWorldObservationFormatterItemTakenFromChest:
    """ItemTakenFromChestEvent のフォーマットテスト"""

    def test_uses_item_repository_when_available(self):
        """item_repository で名前解決できるときアイテム名を表示。"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = WorldObservationFormatter(ctx)
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

    def test_uses_fallback_when_repository_none(self):
        """item_repository が None のときフォールバック名。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
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


class TestWorldObservationFormatterResourceHarvested:
    """ResourceHarvestedEvent のフォーマットテスト"""

    def test_empty_items_returns_base_prose(self):
        """obtained_items が空のとき「採集しました。」"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
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

    def test_with_items_uses_item_spec_repository(self):
        """item_spec_repository で名前解決。"""
        spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "銅の鉱石"
        spec_repo.find_by_id.return_value = spec
        ctx = _make_context(item_spec_repository=spec_repo)
        formatter = WorldObservationFormatter(ctx)
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


class TestWorldObservationFormatterSpotWeatherChanged:
    """SpotWeatherChangedEvent のフォーマットテスト"""

    def test_includes_old_and_new_weather(self):
        """天気変化は old/new を prose に含む。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        event = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Spot",
            spot_id=SpotId(1),
            old_weather_state=WeatherState(WeatherTypeEnum.CLEAR),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "CLEAR" in out.prose or "clear" in out.prose
        assert "RAIN" in out.prose or "rain" in out.prose
        assert out.structured.get("type") == "weather_changed"
        assert out.schedules_turn is True


class TestWorldObservationFormatterWorldObjectInteracted:
    """WorldObjectInteractedEvent のフォーマットテスト"""

    def test_open_chest_returns_prose(self):
        """OPEN_CHEST: 「宝箱を開けました。」"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
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
        assert out.structured.get("interaction_type") == "open_chest"

    def test_examine_with_description_includes_description(self):
        """EXAMINE + data.description: prose に description が含まれる。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.EXAMINE,
            data={"description": "石像の説明文"},
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "調べました" in out.prose
        assert "石像の説明文" in out.prose

    def test_examine_long_description_truncated(self):
        """EXAMINE + 長文: 200文字で truncate。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        long_desc = "あ" * 250
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(2),
            target_id=WorldObjectId(1),
            interaction_type=InteractionTypeEnum.EXAMINE,
            data={"description": long_desc},
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "あ" * 200 in out.prose
        assert "…" in out.prose


class TestWorldObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    def test_returns_none_for_skill_event(self):
        """Skill イベントは None。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestWorldObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_location_exited_does_not_depend_on_recipient(self):
        """LocationExited は recipient に依存しない。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        loc_id = LocationAreaId(1)
        event = LocationExitedEvent.create(
            aggregate_id=loc_id,
            aggregate_type="LocationArea",
            location_id=loc_id,
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose

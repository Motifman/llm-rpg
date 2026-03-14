"""PlayerObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerLocationChangedEvent,
    PlayerLevelUpEvent,
    PlayerRevivedEvent,
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
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.skill.event.skill_events import SkillEquippedEvent
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


def _make_context(
    spot_repository=None,
    player_profile_repository=None,
    item_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=spot_repository,
        player_profile_repository=player_profile_repository,
        item_spec_repository=None,
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


class TestPlayerObservationFormatterCreation:
    """PlayerObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestPlayerObservationFormatterPlayerLocationChanged:
    """PlayerLocationChangedEvent のフォーマットテスト"""

    def test_self_returns_current_location_prose(self):
        """本人向けは「現在地: 〇〇」を返す。"""
        spot_repo = MagicMock()
        spot = MagicMock()
        spot.name = "町の広場"
        spot_repo.find_by_id.return_value = spot
        ctx = _make_context(spot_repository=spot_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "現在地" in out.prose
        assert "町の広場" in out.prose
        assert out.structured.get("type") == "current_location"
        assert out.observation_category == "self_only"

    def test_other_player_returns_entered_spot_prose(self):
        """他プレイヤー向けは「〇〇がこのスポットにやってきました。」"""
        spot_repo = MagicMock()
        spot = MagicMock()
        spot.name = "洞窟入口"
        spot_repo.find_by_id.return_value = spot
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(
            spot_repository=spot_repo,
            player_profile_repository=profile_repo,
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "やってきました" in out.prose
        assert out.structured.get("type") == "player_entered_spot"
        assert out.observation_category == "social"


class TestPlayerObservationFormatterPlayerDowned:
    """PlayerDownedEvent のフォーマットテスト"""

    def test_self_without_killer_returns_downed_prose(self):
        """本人・killer なし: 「戦闘不能になりました。」"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "戦闘不能" in out.prose
        assert out.breaks_movement is True
        assert out.schedules_turn is True

    def test_self_with_killer_includes_killer_name(self):
        """本人・killer あり: 「〇〇に倒されました。」"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Alice" in out.prose
        assert "倒され" in out.prose


class TestPlayerObservationFormatterPlayerRevived:
    """PlayerRevivedEvent のフォーマットテスト"""

    def test_self_returns_revived_prose(self):
        """本人向けは「復帰しました。」"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=50,
            total_hp=100,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "復帰" in out.prose
        assert out.structured.get("type") == "player_revived"


class TestPlayerObservationFormatterPlayerLevelUp:
    """PlayerLevelUpEvent のフォーマットテスト"""

    def test_includes_old_and_new_level(self):
        """old_level と new_level を prose に含む。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "レベル" in out.prose
        assert "1" in out.prose
        assert "2" in out.prose
        assert out.schedules_turn is True


class TestPlayerObservationFormatterItemAddedToInventory:
    """ItemAddedToInventoryEvent のフォーマットテスト"""

    def test_uses_item_repository_for_quantity(self):
        """item_repository で数量を解決。"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        agg.quantity = 3
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "銅の剣" in out.prose
        assert "3個" in out.prose

    def test_fallback_when_repository_none(self):
        """item_repository なしのとき「何かのアイテムを入手」"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "入手" in out.prose


class TestPlayerObservationFormatterPlayerSpoke:
    """PlayerSpokeEvent のフォーマットテスト"""

    def test_say_channel_uses_言った(self):
        """SAY チャンネルは「言った」"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "言った" in out.prose
        assert "こんにちは" in out.prose
        assert out.structured.get("type") == "player_spoke"


class TestPlayerObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return PlayerObservationFormatter(_make_context())

    def test_returns_none_for_skill_event(self, formatter):
        """Skill イベントは None。"""
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestPlayerObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_level_up_does_not_depend_on_recipient(self):
        """PlayerLevelUp は recipient に依存しない（出力は常に本人向け）。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured

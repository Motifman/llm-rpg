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


class TestPlayerObservationFormatterPlayerDownedKillerVisibility:
    """Issue #185: 第三者観測の killer 視認チェック。

    別 spot に killer がいるケースで killer 名を prose に出すと、観測者が
    本来知り得ない「誰が倒したか」を漏らす経路になる。同 spot のときだけ
    killer 名を出す。位置不明 fallback は安全側 (killer 名を出さない)。
    """

    def _make_ctx_with_positions(
        self,
        recipient_spot,
        killer_spot,
        killer_name: str = "Alice",
        victim_name: str = "Victor",
    ):
        """recipient と killer の位置を任意に設定できる context。

        victim (PlayerId=1) と killer (PlayerId=2) で別名を返すよう
        profile_repo.find_by_id を id 別に振り分ける。
        """
        from ai_rpg_world.application.observation.services.formatters._formatter_context import (
            ObservationFormatterContext,
        )

        profile_repo = MagicMock()

        def _find_profile(pid):
            p = MagicMock()
            if pid.value == 1:
                p.name.value = victim_name
            elif pid.value == 2:
                p.name.value = killer_name
            else:
                p.name.value = f"Player{pid.value}"
            return p

        profile_repo.find_by_id.side_effect = _find_profile
        name_resolver = ObservationNameResolver(
            spot_repository=None,
            player_profile_repository=profile_repo,
            item_spec_repository=None,
            item_repository=None,
            shop_repository=None,
            guild_repository=None,
            monster_repository=None,
            skill_spec_repository=None,
            sns_user_repository=None,
        )

        # spot_graph_repository.find_graph().get_entity_spot を player_id 別に返す
        graph = MagicMock()

        def _get_entity_spot(entity_id):
            v = entity_id.value
            if v == 100:  # recipient
                return recipient_spot
            if v == 2:  # killer
                return killer_spot
            return None

        graph.get_entity_spot.side_effect = _get_entity_spot
        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph

        return ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
            spot_graph_repository=spot_repo,
        )

    def test_third_party_same_spot_as_killer_includes_killer_name(self):
        """observer が killer と同 spot に居れば killer 名が prose に出る。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),  # victim
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),  # killer
        )
        out = formatter.format(event, PlayerId(100))  # third-party observer
        assert out is not None
        assert "Alice" in out.prose
        assert "倒され" in out.prose
        assert out.structured["killer_visible_to_recipient"] is True

    def test_third_party_different_spot_from_killer_hides_killer_name(self):
        """observer が killer と別 spot なら killer 名は prose に出ない。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(99)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        # victim の事実 prose
        assert "戦闘不能" in out.prose
        # killer 名は秘匿
        assert "Alice" not in out.prose
        assert out.structured["killer_visible_to_recipient"] is False
        # structured には killer_id を残す (機械可読、解析用)
        assert out.structured["killer_player_id"] == 2

    def test_third_party_position_unknown_hides_killer_name(self):
        """位置不明 (graph 未注入 等) は安全側に倒し killer 名を出さない。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=None, killer_spot=None
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        assert "戦闘不能" in out.prose
        assert "Alice" not in out.prose
        assert out.structured["killer_visible_to_recipient"] is False

    def test_third_party_no_killer_still_outputs_victim_prose(self):
        """killer 不明 (event.killer_player_id=None) は victim 名のみで prose 出す。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            # killer_player_id 未指定
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        assert "戦闘不能" in out.prose
        assert out.structured["killer_visible_to_recipient"] is False


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
        agg.item_spec.item_spec_id.value = 501
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
        assert out.structured.get("item_spec_id_value") == 501

    def test_event_item_spec_id_value_takes_precedence_over_repository(self):
        """イベントの item_spec_id_value があればリポジトリの spec より優先する。"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        agg.item_spec.item_spec_id.value = 501
        agg.quantity = 1
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
            item_spec_id_value=888,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured.get("item_spec_id_value") == 888

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

"""ObservationFormatter のテスト（プローズ・構造化・未知イベント・リポジトリ有無・フォールバック）"""

import pytest
from datetime import datetime
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
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
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
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildMemberJoinedEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestApprovedEvent,
    QuestCancelledEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemPurchasedEvent,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillCooldownStartedEvent,
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    SkillEquippedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillProposalGeneratedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.monster.event.monster_events import (
    BehaviorStuckEvent,
    MonsterDamagedEvent,
    MonsterDecidedToMoveEvent,
    MonsterMpRecoveredEvent,
    MonsterDiedEvent,
    MonsterSpawnedEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.common.value_object import WorldTick


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

    def test_format_player_downed_with_killer_includes_killer_name_or_fallback(self, formatter):
        """PlayerDownedEvent killer_player_id があると「倒された」になる（ID非露出）"""
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "倒され" in out.prose
        assert "プレイヤー2" not in out.prose

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

    def test_format_conversation_started_uses_fallback_npc_name_when_repository_none(self, formatter):
        """ConversationStartedEvent: monster_repository がないと NPC 名はフォールバック"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=999,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "会話を始めました" in out.prose
        assert "誰か" in out.prose
        assert out.observation_category == "self_only"
        assert out.causes_interrupt is True

    def test_format_conversation_started_uses_monster_repository_when_available(self):
        """ConversationStartedEvent: monster_repository で NPC 名が解決できる"""
        monster_repo = MagicMock()
        npc = MagicMock()
        npc.template.name = "老人"
        monster_repo.find_by_world_object_id.return_value = npc
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=None,
            monster_repository=monster_repo,
        )
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "老人" in out.prose
        assert out.structured.get("npc_name") == "老人"

    def test_format_skill_equipped_uses_fallback_when_skill_spec_repository_none(self, formatter):
        """SkillEquippedEvent: skill_spec_repository がないとスキル名はフォールバック"""
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "装備" in out.prose
        assert "何かのスキル" in out.prose

    def test_format_skill_used_uses_skill_spec_repository_when_available(self):
        """SkillUsedEvent: skill_spec_repository があるとスキル名が観測文に入る"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "ファイアボルト"
        skill_spec_repo.find_by_id.return_value = spec
        formatter = ObservationFormatter(
            spot_repository=None,
            player_profile_repository=None,
            skill_spec_repository=skill_spec_repo,
        )
        event = SkillUsedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(1),
            deck_tier=DeckTier.NORMAL,
            cast_lock_until_tick=10,
            cooldown_until_tick=20,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "ファイアボルト" in out.prose
        assert out.causes_interrupt is True

    def test_format_hit_box_hit_recorded_causes_interrupt_and_is_self_only(self, formatter):
        """HitBoxHitRecordedEvent: 命中は割り込み対象"""
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "命中" in out.prose
        assert out.causes_interrupt is True
        assert out.observation_category == "self_only"

    def test_format_monster_spawned_is_environment_and_can_interrupt(self, formatter):
        """MonsterSpawnedEvent: 出現は environment かつ割り込み可"""
        event = MonsterSpawnedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 0, "y": 0, "z": 0},
            spot_id=SpotId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "現れ" in out.prose
        assert out.observation_category == "environment"
        assert out.causes_interrupt is True

    def test_format_monster_died_killer_gets_reward_summary(self, formatter):
        """MonsterDiedEvent: killer 本人には倒した＋報酬概要を含める"""
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=10,
            killer_player_id=PlayerId(1),
            spot_id=SpotId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "倒しました" in out.prose
        assert "ゴールド" in out.prose

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

    def test_format_conversation_ended_includes_rewards_and_unlocks(self, formatter):
        """ConversationEndedEvent: outcome / 報酬 / 解放件数を要約する"""
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            end_node_id_value=1,
            outcome="依頼を受けた",
            rewards_claimed_gold=20,
            rewards_claimed_items=[(1, 2)],
            quest_unlocked_ids=[1, 2],
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "依頼を受けた" in out.prose
        assert "20ゴールド" in out.prose
        assert "新しいクエストが2件" in out.prose

    def test_format_quest_issued_includes_reward_summary(self, formatter):
        """QuestIssuedEvent: 報酬概要がプローズに含まれる"""
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=PlayerId(1),
            scope=QuestScope.public_scope(),
            reward=QuestReward.of(gold=50, exp=12),
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "50ゴールド" in out.prose
        assert "12EXP" in out.prose
        assert out.observation_category == "environment"

    def test_format_quest_pending_approval_is_environment(self, formatter):
        """QuestPendingApprovalEvent: 承認待ち文を返す"""
        event = QuestPendingApprovalEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            guild_id=3,
            issuer_player_id=PlayerId(1),
            scope=QuestScope.guild_scope(3),
            reward=QuestReward.of(gold=5),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "承認待ち" in out.prose
        assert out.observation_category == "environment"

    def test_format_quest_approved_uses_player_repository_name(self):
        """QuestApprovedEvent: 承認者名は player_profile_repository で解決される"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        formatter = ObservationFormatter(player_profile_repository=profile_repo)
        event = QuestApprovedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            approved_by=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Alice" in out.prose
        assert out.structured.get("approved_by") == "Alice"

    def test_format_quest_cancelled_returns_environment_message(self, formatter):
        """QuestCancelledEvent: キャンセル文を返す"""
        event = QuestCancelledEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "キャンセル" in out.prose
        assert out.observation_category == "environment"

    def test_format_shop_created_and_purchased_role_specific_messages(self, formatter):
        """ShopCreatedEvent と ShopItemPurchasedEvent の役割別文言"""
        created = ShopCreatedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            owner_id=PlayerId(3),
        )
        created_out = formatter.format(created, PlayerId(1))
        assert created_out is not None
        assert "開設" in created_out.prose
        buyer_event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId.create(1),
            buyer_id=PlayerId(1),
            quantity=2,
            total_gold=40,
            seller_id=PlayerId(2),
        )
        buyer_out = formatter.format(buyer_event, PlayerId(1))
        seller_out = formatter.format(buyer_event, PlayerId(2))
        assert buyer_out is not None and "購入しました" in buyer_out.prose
        assert seller_out is not None and "購入しました" in seller_out.prose
        assert buyer_out.structured.get("role") == "buyer"
        assert seller_out.structured.get("role") == "seller"

    def test_format_guild_events_use_repository_resolved_names(self):
        """GuildMemberJoined / GuildRoleChanged / GuildBankDeposited は名前解決を使う"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        formatter = ObservationFormatter(player_profile_repository=profile_repo)
        joined = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            membership=GuildMembership(
                player_id=PlayerId(2),
                role=GuildRole.MEMBER,
                joined_at=datetime(2024, 1, 1, 0, 0, 0),
            ),
            invited_by=PlayerId(1),
        )
        joined_out = formatter.format(joined, PlayerId(1))
        assert joined_out is not None
        assert "Bob" in joined_out.prose
        role_changed = GuildRoleChangedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            player_id=PlayerId(2),
            old_role=GuildRole.MEMBER,
            new_role=GuildRole.OFFICER,
            changed_by=PlayerId(1),
        )
        role_out = formatter.format(role_changed, PlayerId(1))
        assert role_out is not None
        assert "officer" in role_out.prose
        deposited = GuildBankDepositedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildBankAggregate",
            amount=100,
            deposited_by=PlayerId(2),
        )
        deposit_out = formatter.format(deposited, PlayerId(1))
        assert deposit_out is not None
        assert "100ゴールド" in deposit_out.prose

    def test_format_harvest_events_return_self_only_messages(self, formatter):
        """HarvestStarted / Cancelled / Completed は self_only で返る"""
        started = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        started_out = formatter.format(started, PlayerId(1))
        assert started_out is not None
        assert started_out.structured.get("finish_tick") == 10
        cancelled = HarvestCancelledEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            reason="moved",
        )
        cancelled_out = formatter.format(cancelled, PlayerId(1))
        assert cancelled_out is not None
        assert "moved" in cancelled_out.prose
        completed = HarvestCompletedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            loot_table_id=LootTableId.create(1),
        )
        completed_out = formatter.format(completed, PlayerId(1))
        assert completed_out is not None
        assert "完了" in completed_out.prose

    def test_format_monster_damaged_returns_environment_message(self, formatter):
        """MonsterDamagedEvent: ダメージ概要を返す"""
        event = MonsterDamagedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            damage=7,
            current_hp=22,
            attacker_id=WorldObjectId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "7ダメージ" in out.prose
        assert out.structured.get("current_hp") == 22

    def test_format_awakened_and_deck_events_return_self_only_outputs(self, formatter):
        """覚醒・デッキ系イベントは self_only で整形される"""
        activated = AwakenedModeActivatedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            activated_at_tick=10,
            expires_at_tick=20,
        )
        activated_out = formatter.format(activated, PlayerId(1))
        assert activated_out is not None
        assert "覚醒モード" in activated_out.prose
        exp_gained = SkillDeckExpGainedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            gained_exp=5,
            total_exp=15,
            deck_level=2,
        )
        exp_out = formatter.format(exp_gained, PlayerId(1))
        assert exp_out is not None
        assert "+5" in exp_out.prose
        leveled = SkillDeckLeveledUpEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            old_level=1,
            new_level=2,
        )
        leveled_out = formatter.format(leveled, PlayerId(1))
        assert leveled_out is not None
        assert leveled_out.causes_interrupt is True

    @pytest.mark.parametrize(
        "event",
        [
            MonsterMpRecoveredEvent.create(
                aggregate_id=MonsterId(1),
                aggregate_type="MonsterAggregate",
                amount=3,
                current_mp=10,
            ),
            MonsterDecidedToMoveEvent.create(
                aggregate_id=MonsterId(1),
                aggregate_type="MonsterAggregate",
                actor_id=WorldObjectId(1),
                coordinate={"x": 0, "y": 0, "z": 0},
                spot_id=SpotId(1),
                current_tick=WorldTick(1),
            ),
            TargetSpottedEvent.create(
                aggregate_id=WorldObjectId(1),
                aggregate_type="MonsterBehavior",
                actor_id=WorldObjectId(1),
                target_id=WorldObjectId(2),
                coordinate=Coordinate(0, 0, 0),
            ),
            BehaviorStuckEvent.create(
                aggregate_id=WorldObjectId(1),
                aggregate_type="MonsterBehavior",
                actor_id=WorldObjectId(1),
                state=BehaviorStateEnum.IDLE,
                coordinate=Coordinate(0, 0, 0),
            ),
            HitBoxCreatedEvent.create(
                aggregate_id=HitBoxId(1),
                aggregate_type="HitBoxAggregate",
                spot_id=SpotId(1),
                owner_id=WorldObjectId(1),
                initial_coordinate=Coordinate(0, 0, 0),
                duration=3,
                power_multiplier=1.0,
                shape_cell_count=1,
                effect_count=0,
                activation_tick=1,
            ),
            HitBoxMovedEvent.create(
                aggregate_id=HitBoxId(1),
                aggregate_type="HitBoxAggregate",
                from_coordinate=Coordinate(0, 0, 0),
                to_coordinate=Coordinate(1, 0, 0),
            ),
            HitBoxDeactivatedEvent.create(
                aggregate_id=HitBoxId(1),
                aggregate_type="HitBoxAggregate",
                reason="expired",
            ),
            HitBoxObstacleCollidedEvent.create(
                aggregate_id=HitBoxId(1),
                aggregate_type="HitBoxAggregate",
                collision_coordinate=Coordinate(1, 0, 0),
                obstacle_collision_policy="stop",
            ),
            SkillCooldownStartedEvent.create(
                aggregate_id=SkillLoadoutId(1),
                aggregate_type="SkillLoadoutAggregate",
                skill_id=SkillId(1),
                cooldown_until_tick=10,
            ),
            SkillProposalGeneratedEvent.create(
                aggregate_id=SkillDeckProgressId(1),
                aggregate_type="SkillDeckProgressAggregate",
                proposal_id=1,
                proposal_type=SkillProposalType.ADD,
                offered_skill_id=SkillId(2),
            ),
        ],
    )
    def test_format_internal_events_returns_none(self, formatter, event):
        """観測対象外の内部イベントは None を返す"""
        assert formatter.format(event, PlayerId(1)) is None

    def test_format_evolution_events_use_skill_repository_name(self):
        """SkillEvolutionAccepted / Rejected はスキル名解決を行う"""
        skill_spec_repo = MagicMock()
        spec = MagicMock()
        spec.name = "ライトニング"
        skill_spec_repo.find_by_id.return_value = spec
        formatter = ObservationFormatter(skill_spec_repository=skill_spec_repo)
        accepted = SkillEvolutionAcceptedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.ADD,
            offered_skill_id=SkillId(2),
        )
        accepted_out = formatter.format(accepted, PlayerId(1))
        rejected = SkillEvolutionRejectedEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            proposal_id=1,
            proposal_type=SkillProposalType.ADD,
            offered_skill_id=SkillId(2),
        )
        rejected_out = formatter.format(rejected, PlayerId(1))
        assert accepted_out is not None and "ライトニング" in accepted_out.prose
        assert rejected_out is not None and "ライトニング" in rejected_out.prose

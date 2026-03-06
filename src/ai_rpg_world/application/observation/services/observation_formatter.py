"""観測テキスト（プローズ＋構造化）を生成するフォーマッタ実装"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationFormatter
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
    GuildCreatedEvent,
    GuildDisbandedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestAcceptedEvent,
    QuestApprovedEvent,
    QuestCancelledEvent,
    QuestCompletedEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopClosedEvent,
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillCooldownStartedEvent,
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEquippedEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillProposalGeneratedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
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
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import SkillSpecRepository


# 名前解決に失敗したときのラベル（ID を露出しない）
FALLBACK_SPOT_LABEL = "不明なスポット"
FALLBACK_PLAYER_LABEL = "不明なプレイヤー"
FALLBACK_ITEM_LABEL = "何かのアイテム"
FALLBACK_NPC_LABEL = "誰か"
FALLBACK_MONSTER_LABEL = "何かのモンスター"
FALLBACK_SKILL_LABEL = "何かのスキル"
FALLBACK_SHOP_LABEL = "どこかのショップ"
FALLBACK_GUILD_LABEL = "どこかのギルド"


class ObservationFormatter(IObservationFormatter):
    """
    イベント＋配信先を観測テキスト（プローズ文と構造化 dict）に変換する。
    仕様の「観測内容（例）」に基づく。名前解決は任意のリポジトリで行う。
    """

    def __init__(
        self,
        spot_repository: Optional["SpotRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        monster_repository: Optional["MonsterRepository"] = None,
        skill_spec_repository: Optional["SkillSpecRepository"] = None,
    ) -> None:
        self._spot_repository = spot_repository
        self._player_profile_repository = player_profile_repository
        self._item_spec_repository = item_spec_repository
        self._item_repository = item_repository
        self._shop_repository = shop_repository
        self._guild_repository = guild_repository
        self._monster_repository = monster_repository
        self._skill_spec_repository = skill_spec_repository

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[AttentionLevel] = None,
    ) -> Optional[ObservationOutput]:
        """指定プレイヤー向けの観測出力を生成。attention_level に応じてスキップする。"""
        output: Optional[ObservationOutput] = None
        if isinstance(event, ConversationStartedEvent):
            output = self._format_conversation_started(event, recipient_player_id)
        elif isinstance(event, ConversationEndedEvent):
            output = self._format_conversation_ended(event, recipient_player_id)
        elif isinstance(event, QuestIssuedEvent):
            output = self._format_quest_issued(event, recipient_player_id)
        elif isinstance(event, QuestAcceptedEvent):
            output = self._format_quest_accepted(event, recipient_player_id)
        elif isinstance(event, QuestCompletedEvent):
            output = self._format_quest_completed(event, recipient_player_id)
        elif isinstance(event, QuestPendingApprovalEvent):
            output = self._format_quest_pending_approval(event, recipient_player_id)
        elif isinstance(event, QuestApprovedEvent):
            output = self._format_quest_approved(event, recipient_player_id)
        elif isinstance(event, QuestCancelledEvent):
            output = self._format_quest_cancelled(event, recipient_player_id)
        elif isinstance(event, ShopCreatedEvent):
            output = self._format_shop_created(event, recipient_player_id)
        elif isinstance(event, ShopItemListedEvent):
            output = self._format_shop_item_listed(event, recipient_player_id)
        elif isinstance(event, ShopItemUnlistedEvent):
            output = self._format_shop_item_unlisted(event, recipient_player_id)
        elif isinstance(event, ShopItemPurchasedEvent):
            output = self._format_shop_item_purchased(event, recipient_player_id)
        elif isinstance(event, ShopClosedEvent):
            output = self._format_shop_closed(event, recipient_player_id)
        elif isinstance(event, GuildCreatedEvent):
            output = self._format_guild_created(event, recipient_player_id)
        elif isinstance(event, GuildMemberJoinedEvent):
            output = self._format_guild_member_joined(event, recipient_player_id)
        elif isinstance(event, GuildMemberLeftEvent):
            output = self._format_guild_member_left(event, recipient_player_id)
        elif isinstance(event, GuildRoleChangedEvent):
            output = self._format_guild_role_changed(event, recipient_player_id)
        elif isinstance(event, GuildBankDepositedEvent):
            output = self._format_guild_bank_deposited(event, recipient_player_id)
        elif isinstance(event, GuildBankWithdrawnEvent):
            output = self._format_guild_bank_withdrawn(event, recipient_player_id)
        elif isinstance(event, GuildDisbandedEvent):
            output = self._format_guild_disbanded(event, recipient_player_id)
        elif isinstance(event, HarvestStartedEvent):
            output = self._format_harvest_started(event, recipient_player_id)
        elif isinstance(event, HarvestCancelledEvent):
            output = self._format_harvest_cancelled(event, recipient_player_id)
        elif isinstance(event, HarvestCompletedEvent):
            output = self._format_harvest_completed(event, recipient_player_id)
        elif isinstance(event, MonsterSpawnedEvent):
            output = self._format_monster_spawned(event, recipient_player_id)
        elif isinstance(event, MonsterRespawnedEvent):
            output = self._format_monster_respawned(event, recipient_player_id)
        elif isinstance(event, MonsterDamagedEvent):
            output = self._format_monster_damaged(event, recipient_player_id)
        elif isinstance(event, MonsterDiedEvent):
            output = self._format_monster_died(event, recipient_player_id)
        elif isinstance(event, MonsterEvadedEvent):
            output = self._format_monster_evaded(event, recipient_player_id)
        elif isinstance(event, MonsterHealedEvent):
            output = self._format_monster_healed(event, recipient_player_id)
        elif isinstance(event, MonsterMpRecoveredEvent):
            output = self._format_monster_mp_recovered(event, recipient_player_id)
        elif isinstance(event, MonsterDecidedToMoveEvent):
            output = self._format_monster_decided_to_move(event, recipient_player_id)
        elif isinstance(event, MonsterDecidedToUseSkillEvent):
            output = self._format_monster_decided_to_use_skill(event, recipient_player_id)
        elif isinstance(event, MonsterDecidedToInteractEvent):
            output = self._format_monster_decided_to_interact(event, recipient_player_id)
        elif isinstance(event, MonsterFedEvent):
            output = self._format_monster_fed(event, recipient_player_id)
        elif isinstance(event, ActorStateChangedEvent):
            output = self._format_actor_state_changed(event, recipient_player_id)
        elif isinstance(event, TargetSpottedEvent):
            output = self._format_target_spotted(event, recipient_player_id)
        elif isinstance(event, TargetLostEvent):
            output = self._format_target_lost(event, recipient_player_id)
        elif isinstance(event, BehaviorStuckEvent):
            output = self._format_behavior_stuck(event, recipient_player_id)
        elif isinstance(event, HitBoxCreatedEvent):
            output = self._format_hit_box_created(event, recipient_player_id)
        elif isinstance(event, HitBoxMovedEvent):
            output = self._format_hit_box_moved(event, recipient_player_id)
        elif isinstance(event, HitBoxHitRecordedEvent):
            output = self._format_hit_box_hit_recorded(event, recipient_player_id)
        elif isinstance(event, HitBoxDeactivatedEvent):
            output = self._format_hit_box_deactivated(event, recipient_player_id)
        elif isinstance(event, HitBoxObstacleCollidedEvent):
            output = self._format_hit_box_obstacle_collided(event, recipient_player_id)
        elif isinstance(event, SkillEquippedEvent):
            output = self._format_skill_equipped(event, recipient_player_id)
        elif isinstance(event, SkillUnequippedEvent):
            output = self._format_skill_unequipped(event, recipient_player_id)
        elif isinstance(event, SkillUsedEvent):
            output = self._format_skill_used(event, recipient_player_id)
        elif isinstance(event, SkillCooldownStartedEvent):
            output = self._format_skill_cooldown_started(event, recipient_player_id)
        elif isinstance(event, AwakenedModeActivatedEvent):
            output = self._format_awakened_mode_activated(event, recipient_player_id)
        elif isinstance(event, AwakenedModeExpiredEvent):
            output = self._format_awakened_mode_expired(event, recipient_player_id)
        elif isinstance(event, SkillLoadoutCapacityChangedEvent):
            output = self._format_skill_loadout_capacity_changed(event, recipient_player_id)
        elif isinstance(event, SkillDeckExpGainedEvent):
            output = self._format_skill_deck_exp_gained(event, recipient_player_id)
        elif isinstance(event, SkillDeckLeveledUpEvent):
            output = self._format_skill_deck_leveled_up(event, recipient_player_id)
        elif isinstance(event, SkillProposalGeneratedEvent):
            output = self._format_skill_proposal_generated(event, recipient_player_id)
        elif isinstance(event, SkillEvolutionAcceptedEvent):
            output = self._format_skill_evolution_accepted(event, recipient_player_id)
        elif isinstance(event, SkillEvolutionRejectedEvent):
            output = self._format_skill_evolution_rejected(event, recipient_player_id)
        elif isinstance(event, MonsterCreatedEvent):
            output = self._format_monster_created(event, recipient_player_id)
        elif isinstance(event, GatewayTriggeredEvent):
            output = self._format_gateway_triggered(event, recipient_player_id)
        elif isinstance(event, LocationEnteredEvent):
            output = self._format_location_entered(event, recipient_player_id)
        elif isinstance(event, LocationExitedEvent):
            output = self._format_location_exited(event, recipient_player_id)
        elif isinstance(event, PlayerLocationChangedEvent):
            output = self._format_player_location_changed(event, recipient_player_id)
        elif isinstance(event, PlayerDownedEvent):
            output = self._format_player_downed(event, recipient_player_id)
        elif isinstance(event, PlayerRevivedEvent):
            output = self._format_player_revived(event, recipient_player_id)
        elif isinstance(event, PlayerLevelUpEvent):
            output = self._format_player_level_up(event, recipient_player_id)
        elif isinstance(event, PlayerGoldEarnedEvent):
            output = self._format_player_gold_earned(event, recipient_player_id)
        elif isinstance(event, PlayerGoldPaidEvent):
            output = self._format_player_gold_paid(event, recipient_player_id)
        elif isinstance(event, ItemTakenFromChestEvent):
            output = self._format_item_taken_from_chest(event, recipient_player_id)
        elif isinstance(event, ItemStoredInChestEvent):
            output = self._format_item_stored_in_chest(event, recipient_player_id)
        elif isinstance(event, ResourceHarvestedEvent):
            output = self._format_resource_harvested(event, recipient_player_id)
        elif isinstance(event, SpotWeatherChangedEvent):
            output = self._format_spot_weather_changed(event, recipient_player_id)
        elif isinstance(event, WorldObjectInteractedEvent):
            output = self._format_world_object_interacted(event, recipient_player_id)
        elif isinstance(event, ItemAddedToInventoryEvent):
            output = self._format_item_added_to_inventory(event, recipient_player_id)
        elif isinstance(event, ItemDroppedFromInventoryEvent):
            output = self._format_item_dropped(event, recipient_player_id)
        elif isinstance(event, ItemEquippedEvent):
            output = self._format_item_equipped(event, recipient_player_id)
        elif isinstance(event, ItemUnequippedEvent):
            output = self._format_item_unequipped(event, recipient_player_id)
        elif isinstance(event, InventorySlotOverflowEvent):
            output = self._format_inventory_slot_overflow(event, recipient_player_id)

        if output is None:
            return None
        # attention_level に応じたフィルタ（FULL または未指定はそのまま）
        if attention_level is None or attention_level == AttentionLevel.FULL:
            return output
        if attention_level == AttentionLevel.FILTER_SOCIAL:
            if output.observation_category == "social":
                return None
        if attention_level == AttentionLevel.IGNORE:
            if output.observation_category != "self_only":
                return None
        return output

    def _spot_name(self, spot_id: SpotId) -> str:
        if self._spot_repository:
            spot = self._spot_repository.find_by_id(spot_id)
            if spot:
                return spot.name
        return FALLBACK_SPOT_LABEL

    def _player_name(self, player_id: PlayerId) -> str:
        if self._player_profile_repository:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile and hasattr(profile, "name"):
                return profile.name.value
        return FALLBACK_PLAYER_LABEL

    def _item_spec_name(self, item_spec_id_value: int) -> str:
        if self._item_spec_repository is None:
            return FALLBACK_ITEM_LABEL
        try:
            from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
            spec_id = ItemSpecId(item_spec_id_value)
        except Exception:
            return FALLBACK_ITEM_LABEL
        spec = self._item_spec_repository.find_by_id(spec_id)
        if spec is not None:
            return spec.name
        return FALLBACK_ITEM_LABEL

    def _item_instance_name(self, item_instance_id: Any) -> str:
        if self._item_repository is None:
            return FALLBACK_ITEM_LABEL
        agg = self._item_repository.find_by_id(item_instance_id)
        if agg is not None:
            return agg.item_spec.name
        return FALLBACK_ITEM_LABEL

    def _format_gateway_triggered(
        self, event: GatewayTriggeredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        target_name = self._spot_name(event.target_spot_id)
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{target_name}に到着しました。"
            structured = {"type": "gateway_arrival", "spot_name": target_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_label = FALLBACK_PLAYER_LABEL if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
        prose = f"{actor_label}がこのスポットにやってきました。"
        structured = {"type": "player_entered_spot", "actor": actor_label, "spot_name": target_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social", causes_interrupt=True
        )

    def _format_location_entered(
        self, event: LocationEnteredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        loc_name = event.name
        is_self = event.player_id_value is not None and event.player_id_value == recipient_id.value
        if is_self:
            prose = f"{loc_name}に着きました。"
            structured = {"type": "location_entered", "location_name": loc_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_label = FALLBACK_PLAYER_LABEL if event.player_id_value is None else self._player_name(PlayerId(event.player_id_value))
        prose = f"{actor_label}が{loc_name}に着きました。"
        structured = {"type": "player_entered_location", "actor": actor_label, "location_name": loc_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_location_exited(
        self, event: LocationExitedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ロケーションを出ました。"
        structured = {"type": "location_exited"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_location_changed(
        self, event: PlayerLocationChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        spot_name = self._spot_name(event.new_spot_id)
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = f"現在地: {spot_name}"
            structured = {"type": "current_location", "spot_name": spot_name, "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}がこのスポットにやってきました。"
        structured = {"type": "player_entered_spot", "actor": actor_name, "spot_name": spot_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_downed(
        self, event: PlayerDownedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        killer_name = (
            self._player_name(event.killer_player_id)
            if getattr(event, "killer_player_id", None) is not None
            else None
        )
        if is_self:
            prose = "戦闘不能になりました。"
            if killer_name:
                prose = f"{killer_name}に倒されました。"
            structured = {"type": "player_downed", "role": "self"}
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True
            )
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}が戦闘不能になりました。"
        if killer_name:
            prose = f"{actor_name}が{killer_name}に倒されました。"
        structured = {"type": "player_downed", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
            return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")
        actor_name = self._player_name(event.aggregate_id)
        prose = f"{actor_name}が復帰しました。"
        structured = {"type": "player_revived", "actor": actor_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_player_level_up(
        self, event: PlayerLevelUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"レベルが上がりました（{event.old_level} → {event.new_level}）。"
        structured = {"type": "level_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_gold_earned(
        self, event: PlayerGoldEarnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.earned_amount}ゴールドを獲得しました。"
        structured = {"type": "gold_earned", "amount": event.earned_amount}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_player_gold_paid(
        self, event: PlayerGoldPaidEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.paid_amount}ゴールドを支払いました。"
        structured = {"type": "gold_paid", "amount": event.paid_amount}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_taken_from_chest(
        self, event: ItemTakenFromChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"チェストから{item_name}を取得しました。"
        structured = {"type": "item_taken_from_chest", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_stored_in_chest(
        self, event: ItemStoredInChestEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"チェストに{item_name}を収納しました。"
        structured = {"type": "item_stored_in_chest", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_resource_harvested(
        self, event: ResourceHarvestedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        parts: list[str] = []
        for entry in event.obtained_items:
            if not isinstance(entry, dict):
                continue
            spec_id_raw = entry.get("item_spec_id")
            qty = entry.get("quantity", 1)
            if spec_id_raw is None:
                parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
                continue
            try:
                spec_id_value = int(spec_id_raw) if not isinstance(spec_id_raw, int) else spec_id_raw
            except (TypeError, ValueError):
                parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
                continue
            name = self._item_spec_name(spec_id_value)
            parts.append(f"{name}を{qty}個")
        if not parts:
            prose = "採集しました。"
            structured = {"type": "resource_harvested", "items": []}
        else:
            item_desc = "、".join(parts)
            prose = f"採集し、{item_desc}入手しました。"
            structured = {"type": "resource_harvested", "items": event.obtained_items}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        old_s = event.old_weather_state.weather_type.value
        new_s = event.new_weather_state.weather_type.value
        prose = f"天気が{old_s}から{new_s}に変わりました。"
        structured = {"type": "weather_changed", "old": old_s, "new": new_s}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _interaction_type_to_prose(self, interaction_type: InteractionTypeEnum, data: Dict[str, Any]) -> str:
        """interaction_type を LLM 向けの 5W1H 観測文に変換する。"""
        if interaction_type == InteractionTypeEnum.OPEN_CHEST:
            return "宝箱を開けました。"
        if interaction_type == InteractionTypeEnum.OPEN_DOOR:
            is_open = data.get("is_open") if isinstance(data, dict) else None
            if is_open is True:
                return "ドアを開きました。"
            if is_open is False:
                return "ドアを閉めました。"
            return "ドアを操作しました。"
        if interaction_type == InteractionTypeEnum.HARVEST:
            return "資源を採取しました。"
        if interaction_type == InteractionTypeEnum.TALK:
            return "話しかけました。"
        if interaction_type == InteractionTypeEnum.EXAMINE:
            return "調べました。"
        if interaction_type == InteractionTypeEnum.STORE_IN_CHEST:
            return "チェストに収納しました。"
        if interaction_type == InteractionTypeEnum.TAKE_FROM_CHEST:
            return "チェストから取得しました。"
        if interaction_type == InteractionTypeEnum.MONSTER_FEED:
            return "餌を与えました。"
        return "何かに触れました。"

    def _format_world_object_interacted(
        self, event: WorldObjectInteractedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = self._interaction_type_to_prose(event.interaction_type, event.data or {})
        structured = {
            "type": "object_interacted",
            "interaction_type": event.interaction_type.value,
        }
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_added_to_inventory(
        self, event: ItemAddedToInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        agg = None
        if self._item_repository:
            agg = self._item_repository.find_by_id(event.item_instance_id)
        qty = agg.quantity if agg is not None else 1
        if qty != 1:
            prose = f"{item_name}を{qty}個入手しました。"
        else:
            prose = f"{item_name}を入手しました。"
        structured = {"type": "item_added_to_inventory", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True
        )

    def _format_item_dropped(
        self, event: ItemDroppedFromInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を捨てました。"
        structured = {"type": "item_dropped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_equipped(
        self, event: ItemEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を装備しました。"
        structured = {"type": "item_equipped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_item_unequipped(
        self, event: ItemUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"{item_name}を外しました。"
        structured = {"type": "item_unequipped", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_inventory_slot_overflow(
        self, event: InventorySlotOverflowEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.overflowed_item_instance_id)
        prose = f"インベントリが満杯で{item_name}が溢れました。"
        structured = {"type": "inventory_overflow", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    # --- 会話 ---

    def _npc_name(self, npc_id_value: int) -> str:
        if self._monster_repository is None:
            return FALLBACK_NPC_LABEL
        try:
            from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

            npc_object_id = WorldObjectId(npc_id_value)
        except Exception:
            return FALLBACK_NPC_LABEL
        npc = self._monster_repository.find_by_world_object_id(npc_object_id)
        if npc is None:
            return FALLBACK_NPC_LABEL
        return npc.template.name or FALLBACK_NPC_LABEL

    def _format_conversation_started(
        self, event: ConversationStartedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        npc_name = self._npc_name(event.npc_id_value)
        prose = f"{npc_name}と会話を始めました。"
        structured = {"type": "conversation_started", "npc_name": npc_name}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            causes_interrupt=True,
        )

    def _format_conversation_ended(
        self, event: ConversationEndedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        npc_name = self._npc_name(event.npc_id_value)
        parts: list[str] = [f"{npc_name}との会話を終えました。"]
        if event.outcome:
            parts.append(str(event.outcome))
        if event.rewards_claimed_gold:
            parts.append(f"{event.rewards_claimed_gold}ゴールドを獲得しました。")
        if event.rewards_claimed_items:
            item_parts: list[str] = []
            for spec_id_value, qty in event.rewards_claimed_items:
                name = self._item_spec_name(spec_id_value)
                item_parts.append(f"{name}を{qty}個")
            if item_parts:
                parts.append("報酬: " + "、".join(item_parts))
        if event.quest_unlocked_ids:
            parts.append(f"新しいクエストが{len(event.quest_unlocked_ids)}件解放されました。")
        prose = " ".join(parts)
        structured = {
            "type": "conversation_ended",
            "npc_name": npc_name,
            "outcome": event.outcome,
            "rewards_claimed_gold": event.rewards_claimed_gold,
            "rewards_claimed_items": list(event.rewards_claimed_items),
            "quest_unlocked_count": len(event.quest_unlocked_ids),
        }
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    # --- クエスト ---

    def _quest_reward_summary(self, reward: Any) -> str:
        # QuestReward.gold/exp/item_rewards を想定（型安全よりフォールバック優先）
        gold = getattr(reward, "gold", 0) or 0
        exp = getattr(reward, "exp", 0) or 0
        item_rewards = getattr(reward, "item_rewards", ()) or ()
        parts: list[str] = []
        if gold:
            parts.append(f"{gold}ゴールド")
        if exp:
            parts.append(f"{exp}EXP")
        item_parts: list[str] = []
        for item_spec_id, qty in item_rewards:
            try:
                spec_id_value = int(getattr(item_spec_id, "value", item_spec_id))
            except Exception:
                spec_id_value = None
            if spec_id_value is None:
                item_parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
            else:
                item_parts.append(f"{self._item_spec_name(spec_id_value)}を{qty}個")
        if item_parts:
            parts.append("、".join(item_parts))
        return "、".join(parts) if parts else ""

    def _format_quest_issued(self, event: QuestIssuedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "新しいクエストが発行されました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        structured = {"type": "quest_issued", "reward": {"gold": event.reward.gold, "exp": event.reward.exp}}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment", causes_interrupt=True)

    def _format_quest_accepted(self, event: QuestAcceptedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "クエストを受託しました。"
        structured = {"type": "quest_accepted"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_quest_completed(self, event: QuestCompletedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "クエストを完了しました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        structured = {"type": "quest_completed", "reward": {"gold": event.reward.gold, "exp": event.reward.exp}}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_quest_pending_approval(self, event: QuestPendingApprovalEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "クエストが承認待ちになりました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        structured = {"type": "quest_pending_approval", "guild_id": event.guild_id}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_quest_approved(self, event: QuestApprovedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        actor = self._player_name(event.approved_by)
        prose = f"クエストが承認されました（承認者: {actor}）。"
        structured = {"type": "quest_approved", "approved_by": actor}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_quest_cancelled(self, event: QuestCancelledEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "クエストがキャンセルされました。"
        structured = {"type": "quest_cancelled"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    # --- ショップ ---

    def _shop_name(self, shop_id: Any) -> str:
        if self._shop_repository is None:
            return FALLBACK_SHOP_LABEL
        shop = self._shop_repository.find_by_id(shop_id)
        if shop is None:
            return FALLBACK_SHOP_LABEL
        return shop.name.strip() if getattr(shop, "name", "").strip() else FALLBACK_SHOP_LABEL

    def _format_shop_created(self, event: ShopCreatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "ショップが開設されました。"
        structured = {"type": "shop_created"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_shop_item_listed(self, event: ShopItemListedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        prose = f"ショップに{item_name}が出品されました。"
        structured = {"type": "shop_item_listed", "item_name": item_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_shop_item_unlisted(self, event: ShopItemUnlistedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "ショップの出品が取り下げられました。"
        structured = {"type": "shop_item_unlisted"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_shop_item_purchased(self, event: ShopItemPurchasedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        item_name = self._item_instance_name(event.item_instance_id)
        is_buyer = event.buyer_id.value == recipient_id.value
        buyer_name = self._player_name(event.buyer_id)
        seller_name = self._player_name(event.seller_id)
        if is_buyer:
            prose = f"{item_name}を{event.quantity}個購入しました（支払い: {event.total_gold}ゴールド）。"
            structured = {"type": "shop_purchase", "role": "buyer", "item_name": item_name}
        else:
            prose = f"{buyer_name}が{item_name}を{event.quantity}個購入しました（受取: {event.total_gold}ゴールド）。"
            structured = {"type": "shop_purchase", "role": "seller", "item_name": item_name, "buyer": buyer_name, "seller": seller_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_shop_closed(self, event: ShopClosedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "ショップが閉鎖されました。"
        structured = {"type": "shop_closed"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    # --- ギルド ---

    def _guild_name(self, guild_id: Any) -> str:
        if self._guild_repository is None:
            return FALLBACK_GUILD_LABEL
        guild = self._guild_repository.find_by_id(guild_id)
        if guild is None:
            return FALLBACK_GUILD_LABEL
        return guild.name.strip() if getattr(guild, "name", "").strip() else FALLBACK_GUILD_LABEL

    def _format_guild_created(self, event: GuildCreatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"ギルド「{event.name}」が創設されました。"
        structured = {"type": "guild_created", "guild_name": event.name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_guild_member_joined(self, event: GuildMemberJoinedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        member_name = self._player_name(event.membership.player_id)
        prose = f"{member_name}がギルドに加入しました。"
        structured = {"type": "guild_member_joined", "member": member_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social", causes_interrupt=True)

    def _format_guild_member_left(self, event: GuildMemberLeftEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        member_name = self._player_name(event.player_id)
        prose = f"{member_name}がギルドから脱退しました。"
        structured = {"type": "guild_member_left", "member": member_name, "role": event.role.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_guild_role_changed(self, event: GuildRoleChangedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        member_name = self._player_name(event.player_id)
        prose = f"{member_name}の役職が{event.old_role.value}から{event.new_role.value}に変わりました。"
        structured = {"type": "guild_role_changed", "member": member_name, "old": event.old_role.value, "new": event.new_role.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_guild_bank_deposited(self, event: GuildBankDepositedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        actor = self._player_name(event.deposited_by)
        prose = f"{actor}がギルド金庫に{event.amount}ゴールドを入金しました。"
        structured = {"type": "guild_bank_deposited", "amount": event.amount, "by": actor}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_guild_bank_withdrawn(self, event: GuildBankWithdrawnEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        actor = self._player_name(event.withdrawn_by)
        prose = f"{actor}がギルド金庫から{event.amount}ゴールドを出金しました。"
        structured = {"type": "guild_bank_withdrawn", "amount": event.amount, "by": actor}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social")

    def _format_guild_disbanded(self, event: GuildDisbandedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "ギルドが解散しました。"
        structured = {"type": "guild_disbanded"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="social", causes_interrupt=True)

    # --- Harvest ---

    def _format_harvest_started(self, event: HarvestStartedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "採集を開始しました。"
        structured = {"type": "harvest_started", "finish_tick": int(getattr(event.finish_tick, "value", event.finish_tick))}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_harvest_cancelled(self, event: HarvestCancelledEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"採集を中断しました（理由: {event.reason}）。"
        structured = {"type": "harvest_cancelled", "reason": event.reason}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_harvest_completed(self, event: HarvestCompletedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "採集が完了しました。"
        structured = {"type": "harvest_completed"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    # --- Monster ---

    def _monster_name_by_monster_id(self, monster_id: Any) -> str:
        if self._monster_repository is None:
            return FALLBACK_MONSTER_LABEL
        monster = self._monster_repository.find_by_id(monster_id)
        if monster is None:
            return FALLBACK_MONSTER_LABEL
        return monster.template.name or FALLBACK_MONSTER_LABEL

    def _format_monster_created(self, event: MonsterCreatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        # システム内部向け。観測は出さない。
        return None

    def _format_monster_spawned(self, event: MonsterSpawnedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "モンスターが現れました。"
        structured = {"type": "monster_spawned"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment", causes_interrupt=True)

    def _format_monster_respawned(self, event: MonsterRespawnedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "モンスターが再出現しました。"
        structured = {"type": "monster_respawned"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_damaged(self, event: MonsterDamagedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"モンスターに{event.damage}ダメージ。"
        structured = {"type": "monster_damaged", "damage": event.damage, "current_hp": event.current_hp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_died(self, event: MonsterDiedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "モンスターが倒れました。"
        if event.killer_player_id is not None and event.killer_player_id.value == recipient_id.value:
            prose = f"モンスターを倒しました（報酬: {event.gold}ゴールド、{event.exp}EXP）。"
        structured = {"type": "monster_died", "gold": event.gold, "exp": event.exp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment", causes_interrupt=True)

    def _format_monster_evaded(self, event: MonsterEvadedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "モンスターが回避しました。"
        structured = {"type": "monster_evaded"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_healed(self, event: MonsterHealedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"モンスターが回復しました（+{event.amount}）。"
        structured = {"type": "monster_healed", "amount": event.amount, "current_hp": event.current_hp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_mp_recovered(self, event: MonsterMpRecoveredEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_move(self, event: MonsterDecidedToMoveEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_use_skill(self, event: MonsterDecidedToUseSkillEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_interact(self, event: MonsterDecidedToInteractEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_monster_fed(self, event: MonsterFedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "モンスターが採食しました。"
        structured = {"type": "monster_fed"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_actor_state_changed(self, event: ActorStateChangedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"モンスターの状態が{event.old_state.value}から{event.new_state.value}に変化しました。"
        structured = {"type": "monster_state_changed", "old": event.old_state.value, "new": event.new_state.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_target_spotted(self, event: TargetSpottedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_target_lost(self, event: TargetLostEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_behavior_stuck(self, event: BehaviorStuckEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    # --- Combat (HitBox) ---

    def _format_hit_box_created(self, event: HitBoxCreatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_moved(self, event: HitBoxMovedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_hit_recorded(self, event: HitBoxHitRecordedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "攻撃が命中しました。"
        structured = {"type": "hitbox_hit"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_hit_box_deactivated(self, event: HitBoxDeactivatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_hit_box_obstacle_collided(self, event: HitBoxObstacleCollidedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    # --- Skill ---

    def _skill_name(self, skill_id: Any) -> str:
        if self._skill_spec_repository is None:
            return FALLBACK_SKILL_LABEL
        spec = self._skill_spec_repository.find_by_id(skill_id)
        if spec is None:
            return FALLBACK_SKILL_LABEL
        return spec.name or FALLBACK_SKILL_LABEL

    def _format_skill_equipped(self, event: SkillEquippedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        name = self._skill_name(event.skill_id)
        prose = f"{name}を装備しました。"
        structured = {"type": "skill_equipped", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_unequipped(self, event: SkillUnequippedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        name = self._skill_name(event.removed_skill_id)
        prose = f"{name}を外しました。"
        structured = {"type": "skill_unequipped", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_used(self, event: SkillUsedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        name = self._skill_name(event.skill_id)
        prose = f"{name}を使用しました。"
        structured = {"type": "skill_used", "skill_name": name, "deck_tier": event.deck_tier.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_skill_cooldown_started(self, event: SkillCooldownStartedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_awakened_mode_activated(self, event: AwakenedModeActivatedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "覚醒モードが発動しました。"
        structured = {"type": "awakened_mode_activated", "expires_at_tick": event.expires_at_tick}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_awakened_mode_expired(self, event: AwakenedModeExpiredEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = "覚醒モードが終了しました。"
        structured = {"type": "awakened_mode_expired"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_loadout_capacity_changed(self, event: SkillLoadoutCapacityChangedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"スキルデッキの容量が更新されました（通常:{event.normal_capacity}、覚醒:{event.awakened_capacity}）。"
        structured = {"type": "skill_loadout_capacity_changed", "normal": event.normal_capacity, "awakened": event.awakened_capacity}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_deck_exp_gained(self, event: SkillDeckExpGainedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"スキルデッキに経験値を獲得しました（+{event.gained_exp}）。"
        structured = {"type": "skill_deck_exp_gained", "gained_exp": event.gained_exp, "total_exp": event.total_exp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_deck_leveled_up(self, event: SkillDeckLeveledUpEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        prose = f"スキルデッキがレベルアップしました（{event.old_level}→{event.new_level}）。"
        structured = {"type": "skill_deck_leveled_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only", causes_interrupt=True)

    def _format_skill_proposal_generated(self, event: SkillProposalGeneratedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        return None

    def _format_skill_evolution_accepted(self, event: SkillEvolutionAcceptedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        skill_name = self._skill_name(event.offered_skill_id)
        prose = f"スキル進化を受諾しました（{skill_name}）。"
        structured = {"type": "skill_evolution_accepted", "skill_name": skill_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_skill_evolution_rejected(self, event: SkillEvolutionRejectedEvent, recipient_id: PlayerId) -> Optional[ObservationOutput]:
        skill_name = self._skill_name(event.offered_skill_id)
        prose = f"スキル進化を拒否しました（{skill_name}）。"
        structured = {"type": "skill_evolution_rejected", "skill_name": skill_name}
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

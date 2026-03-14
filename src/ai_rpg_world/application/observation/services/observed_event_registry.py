"""
観測対象イベントの一元的な定義。

観測するイベントかどうかの判定を一箇所に集約し、
新イベント追加時の formatter / recipient strategy 間の同期負担を軽減する。

参照: docs/refactoring/phase2-3-refactoring-plan.md Phase A2
"""

from typing import Any, Dict, Optional, Type, Tuple

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
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    PlayerLevelUpEvent,
    PlayerLocationChangedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
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
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.world.event.map_events import (
    ItemStoredInChestEvent,
    ItemTakenFromChestEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)


def _build_event_to_strategy_mapping() -> Dict[Type[Any], str]:
    """観測対象イベント型と担当戦略のマッピングを構築する。"""
    mapping: Dict[Type[Any], str] = {}

    # conversation (順序: Resolver の先頭)
    for ev in (ConversationStartedEvent, ConversationEndedEvent):
        mapping[ev] = "conversation"

    # quest
    for ev in (
        QuestIssuedEvent,
        QuestAcceptedEvent,
        QuestCompletedEvent,
        QuestPendingApprovalEvent,
        QuestApprovedEvent,
        QuestCancelledEvent,
    ):
        mapping[ev] = "quest"

    # shop
    for ev in (
        ShopCreatedEvent,
        ShopItemListedEvent,
        ShopItemUnlistedEvent,
        ShopItemPurchasedEvent,
        ShopClosedEvent,
    ):
        mapping[ev] = "shop"

    # trade
    for ev in (
        TradeOfferedEvent,
        TradeAcceptedEvent,
        TradeCancelledEvent,
        TradeDeclinedEvent,
    ):
        mapping[ev] = "trade"

    # sns
    for ev in (
        SnsPostCreatedEvent,
        SnsReplyCreatedEvent,
        SnsContentLikedEvent,
        SnsUserFollowedEvent,
        SnsUserSubscribedEvent,
    ):
        mapping[ev] = "sns"

    # guild
    for ev in (
        GuildCreatedEvent,
        GuildMemberJoinedEvent,
        GuildMemberLeftEvent,
        GuildRoleChangedEvent,
        GuildBankDepositedEvent,
        GuildBankWithdrawnEvent,
        GuildDisbandedEvent,
    ):
        mapping[ev] = "guild"

    # harvest
    for ev in (HarvestStartedEvent, HarvestCancelledEvent, HarvestCompletedEvent):
        mapping[ev] = "harvest"

    # pursuit
    for ev in (
        PursuitStartedEvent,
        PursuitUpdatedEvent,
        PursuitFailedEvent,
        PursuitCancelledEvent,
    ):
        mapping[ev] = "pursuit"

    # monster
    for ev in (
        MonsterCreatedEvent,
        MonsterSpawnedEvent,
        MonsterDamagedEvent,
        MonsterDiedEvent,
        MonsterRespawnedEvent,
        MonsterEvadedEvent,
        MonsterHealedEvent,
        MonsterMpRecoveredEvent,
        MonsterDecidedToMoveEvent,
        MonsterDecidedToUseSkillEvent,
        MonsterDecidedToInteractEvent,
        MonsterFedEvent,
        ActorStateChangedEvent,
        TargetSpottedEvent,
        TargetLostEvent,
        BehaviorStuckEvent,
    ):
        mapping[ev] = "monster"

    # combat
    for ev in (
        HitBoxCreatedEvent,
        HitBoxMovedEvent,
        HitBoxHitRecordedEvent,
        HitBoxDeactivatedEvent,
        HitBoxObstacleCollidedEvent,
    ):
        mapping[ev] = "combat"

    # skill
    for ev in (
        SkillEquippedEvent,
        SkillUnequippedEvent,
        SkillUsedEvent,
        SkillCooldownStartedEvent,
        AwakenedModeActivatedEvent,
        AwakenedModeExpiredEvent,
        SkillLoadoutCapacityChangedEvent,
        SkillDeckExpGainedEvent,
        SkillDeckLeveledUpEvent,
        SkillProposalGeneratedEvent,
        SkillEvolutionAcceptedEvent,
        SkillEvolutionRejectedEvent,
    ):
        mapping[ev] = "skill"

    # speech
    mapping[PlayerSpokeEvent] = "speech"

    # default (Gateway / マップ / プレイヤー状態 / インベントリ系)
    for ev in (
        LocationEnteredEvent,
        LocationExitedEvent,
        PlayerLocationChangedEvent,
        PlayerDownedEvent,
        PlayerRevivedEvent,
        PlayerLevelUpEvent,
        PlayerGoldEarnedEvent,
        PlayerGoldPaidEvent,
        ItemTakenFromChestEvent,
        ItemStoredInChestEvent,
        ResourceHarvestedEvent,
        SpotWeatherChangedEvent,
        WorldObjectInteractedEvent,
        ItemAddedToInventoryEvent,
        ItemDroppedFromInventoryEvent,
        ItemEquippedEvent,
        ItemUnequippedEvent,
        InventorySlotOverflowEvent,
    ):
        mapping[ev] = "default"

    return mapping


_EVENT_TO_STRATEGY: Dict[Type[Any], str] = _build_event_to_strategy_mapping()


class ObservedEventRegistry:
    """
    観測対象イベントのレジストリ。

    イベント型ごとに担当 recipient strategy のキーを保持し、
    観測対象かどうかの判定および戦略の解決を提供する。
    """

    def __init__(
        self,
        event_to_strategy: Optional[Dict[Type[Any], str]] = None,
    ) -> None:
        """
        Args:
            event_to_strategy: カスタムマッピング。None の場合はデフォルトを使用。
        """
        self._event_to_strategy = (
            event_to_strategy if event_to_strategy is not None else dict(_EVENT_TO_STRATEGY)
        )

    def is_observed(self, event: Any) -> bool:
        """イベントが観測対象の場合 True を返す。"""
        if event is None:
            return False
        return type(event) in self._event_to_strategy

    def get_strategy_for_event(self, event: Any) -> Optional[str]:
        """
        イベントを担当する recipient strategy のキーを返す。
        観測対象外の場合は None。
        """
        if event is None:
            return None
        return self._event_to_strategy.get(type(event))

    def get_event_types_for_strategy(self, strategy_key: str) -> Tuple[Type[Any], ...]:
        """
        指定 strategy が担当するイベント型のタプルを返す。
        テスト・デバッグ用。
        """
        return tuple(
            ev_type for ev_type, key in self._event_to_strategy.items() if key == strategy_key
        )

"""観測用イベントハンドラを EventPublisher に登録する Registry"""

from ai_rpg_world.application.observation.handlers.observation_event_handler import ObservationEventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxHitRecordedEvent,
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
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
)
from ai_rpg_world.domain.world.event.map_events import (
    LocationEnteredEvent,
    LocationExitedEvent,
    ItemTakenFromChestEvent,
    ItemStoredInChestEvent,
    ResourceHarvestedEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
)
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    HarvestStartedEvent,
)
from ai_rpg_world.domain.player.event.status_events import (
    PlayerLocationChangedEvent,
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
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
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEquippedEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)

# 観測対象イベント型一覧（仕様に基づく）
_OBSERVED_EVENT_TYPES = (
    # --- 会話 ---
    ConversationStartedEvent,
    ConversationEndedEvent,
    PlayerSpokeEvent,
    # --- クエスト ---
    QuestIssuedEvent,
    QuestAcceptedEvent,
    QuestCompletedEvent,
    QuestPendingApprovalEvent,
    QuestApprovedEvent,
    QuestCancelledEvent,
    # --- ショップ ---
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
    ShopItemPurchasedEvent,
    ShopClosedEvent,
    # --- トレード ---
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    # --- SNS ---
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
    # --- ギルド ---
    GuildCreatedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
    GuildDisbandedEvent,
    # --- 採集 ---
    HarvestStartedEvent,
    HarvestCancelledEvent,
    HarvestCompletedEvent,
    # --- モンスター ---
    MonsterSpawnedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterRespawnedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterFedEvent,
    ActorStateChangedEvent,
    # --- 戦闘 ---
    HitBoxHitRecordedEvent,
    # --- スキル ---
    SkillEquippedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    # --- 既存 ---
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
    # --- 追跡 ---
    PursuitStartedEvent,
    PursuitUpdatedEvent,
    PursuitFailedEvent,
    PursuitCancelledEvent,
)


class ObservationEventHandlerRegistry:
    """観測用ハンドラを全観測対象イベント型に登録する"""

    def __init__(self, observation_handler: ObservationEventHandler) -> None:
        self._handler = observation_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全観測対象イベント型に対して同一ハンドラを非同期で登録する"""
        for event_type in _OBSERVED_EVENT_TYPES:
            event_publisher.register_handler(
                event_type,
                self._handler,
                is_synchronous=False,
            )

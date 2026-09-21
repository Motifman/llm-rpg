"""プレイヤーの runtime context（インベントリ・会話・クエスト・スキル等）を構築する facade。

PlayerSupplementalContextBuilder を委譲先として持ち、LLM の runtime で利用する
read model 構築責務を明示する名前を提供する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    ActiveQuestSummaryDto,
    AttentionLevelOptionDto,
    AvailableTradeSummaryDto,
    AwakenedActionDto,
    ChestItemDto,
    EquipableSkillCandidateDto,
    GuildMembershipSummaryDto,
    InventoryItemDto,
    NearbyShopSummaryDto,
    PendingSkillProposalDto,
    SkillEquipSlotDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.application.world.services.player_supplemental_context_builder import (
    PlayerSupplementalContextBuilder,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.player.repository.player_inventory_repository import (
        PlayerInventoryRepository,
    )
    from ai_rpg_world.domain.player.repository.player_profile_repository import (
        PlayerProfileRepository,
    )
    from ai_rpg_world.domain.player.repository.player_status_repository import (
        PlayerStatusRepository,
    )
    from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import (
        SkillDeckProgressRepository,
        SkillLoadoutRepository,
    )
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
        PhysicalMapAggregate,
    )


class PlayerRuntimeContextBuilder:
    """LLM runtime で利用するインベントリ・会話・クエスト・ギルド・ショップ・取引・スキル等の read model を構築する。

    PlayerSupplementalContextBuilder を委譲先として持ち、責務の境界を名前で明示する。
    """

    def __init__(
        self,
        supplemental_context_builder: PlayerSupplementalContextBuilder | None = None,
        player_inventory_repository: PlayerInventoryRepository | None = None,
        item_repository: ItemRepository | None = None,
        conversation_command_service: ConversationCommandService | None = None,
        skill_loadout_repository: SkillLoadoutRepository | None = None,
        skill_deck_progress_repository: SkillDeckProgressRepository | None = None,
        game_time_provider: GameTimeProvider | None = None,
        quest_repository: QuestRepository | None = None,
        guild_repository: GuildRepository | None = None,
        shop_repository: ShopRepository | None = None,
        personal_trade_query_service: PersonalTradeQueryService | None = None,
        player_profile_repository: PlayerProfileRepository | None = None,
        player_status_repository: PlayerStatusRepository | None = None,
    ) -> None:
        self._supplemental_context_builder = (
            supplemental_context_builder
            or PlayerSupplementalContextBuilder(
                player_inventory_repository=player_inventory_repository,
                item_repository=item_repository,
                conversation_command_service=conversation_command_service,
                skill_loadout_repository=skill_loadout_repository,
                skill_deck_progress_repository=skill_deck_progress_repository,
                game_time_provider=game_time_provider,
                quest_repository=quest_repository,
                guild_repository=guild_repository,
                shop_repository=shop_repository,
                personal_trade_query_service=personal_trade_query_service,
                player_profile_repository=player_profile_repository,
                player_status_repository=player_status_repository,
            )
        )

    def build_inventory_items(self, player_id: PlayerId) -> list[InventoryItemDto]:
        return self._supplemental_context_builder.build_inventory_items(player_id)

    def build_chest_items(
        self,
        physical_map: PhysicalMapAggregate,
        visible_objects: list[VisibleObjectDto],
    ) -> list[ChestItemDto]:
        return self._supplemental_context_builder.build_chest_items(
            physical_map, visible_objects
        )

    def build_active_conversation(
        self,
        player_id: int,
        visible_objects: list[VisibleObjectDto],
    ) -> ActiveConversationDto | None:
        return self._supplemental_context_builder.build_active_conversation(
            player_id, visible_objects
        )

    def build_active_quest_ids(self, player_id: int) -> list[int]:
        return self._supplemental_context_builder.build_active_quest_ids(player_id)

    def build_guild_ids(self, player_id: int) -> list[int]:
        return self._supplemental_context_builder.build_guild_ids(player_id)

    def build_nearby_shop_ids(
        self, spot_id: int, location_area_ids: list[int] | None = None
    ) -> list[int]:
        return self._supplemental_context_builder.build_nearby_shop_ids(
            spot_id, location_area_ids
        )

    def build_active_quests(self, player_id: int) -> list[ActiveQuestSummaryDto]:
        return self._supplemental_context_builder.build_active_quests(player_id)

    def build_guild_memberships(
        self, player_id: int, player_area_ids: list[int] | None = None
    ) -> list[GuildMembershipSummaryDto]:
        return self._supplemental_context_builder.build_guild_memberships(
            player_id, player_area_ids
        )

    def build_nearby_shops(
        self, spot_id: int, location_area_ids: list[int] | None = None
    ) -> list[NearbyShopSummaryDto]:
        return self._supplemental_context_builder.build_nearby_shops(
            spot_id, location_area_ids
        )

    def build_available_trades(
        self, player_id: int, limit: int = 5
    ) -> list[AvailableTradeSummaryDto]:
        return self._supplemental_context_builder.build_available_trades(
            player_id, limit
        )

    def build_usable_skills(self, player_id: int) -> list[UsableSkillDto]:
        return self._supplemental_context_builder.build_usable_skills(player_id)

    def build_equipable_skill_candidates(
        self, player_id: int
    ) -> list[EquipableSkillCandidateDto]:
        return self._supplemental_context_builder.build_equipable_skill_candidates(
            player_id
        )

    def build_skill_equip_slots(self, player_id: int) -> list[SkillEquipSlotDto]:
        return self._supplemental_context_builder.build_skill_equip_slots(player_id)

    def build_pending_skill_proposals(self, player_id: int) -> list[PendingSkillProposalDto]:
        return self._supplemental_context_builder.build_pending_skill_proposals(
            player_id
        )

    def build_awakened_action(self, player_id: int) -> AwakenedActionDto | None:
        return self._supplemental_context_builder.build_awakened_action(player_id)

    def build_attention_level_options(self) -> list[AttentionLevelOptionDto]:
        return self._supplemental_context_builder.build_attention_level_options()

    def can_destroy_placeable(self, physical_map: PhysicalMapAggregate, player_id: int) -> bool:
        return self._supplemental_context_builder.can_destroy_placeable(
            physical_map, player_id
        )

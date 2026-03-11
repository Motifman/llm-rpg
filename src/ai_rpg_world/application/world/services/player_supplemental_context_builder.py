"""プレイヤー現在状態の補助文脈を構築する。"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    ActiveQuestSummaryDto,
    AttentionLevelOptionDto,
    AvailableTradeSummaryDto,
    ChestItemDto,
    ConversationChoiceDto,
    GuildMemberSummaryDto,
    GuildMembershipSummaryDto,
    InventoryItemDto,
    NearbyShopSummaryDto,
    ShopListingSummaryDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.application.trade.exceptions import (
    PersonalTradeQueryApplicationException,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.entity.world_object_component import (
    ChestComponent,
    PlaceableComponent,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    NotAnActorException,
    ObjectNotFoundException,
    WorldObjectIdValidationException,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import (
        PlayerProfileRepository,
    )
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.player.repository.player_inventory_repository import (
        PlayerInventoryRepository,
    )
    from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )


class PlayerSupplementalContextBuilder:
    """inventory / chest / conversation / skill / attention / guild / shop の read model を構築する。"""

    def __init__(
        self,
        player_inventory_repository: Optional["PlayerInventoryRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        conversation_command_service: Optional["ConversationCommandService"] = None,
        skill_loadout_repository: Optional["SkillLoadoutRepository"] = None,
        game_time_provider: Optional["GameTimeProvider"] = None,
        quest_repository: Optional["QuestRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        personal_trade_query_service: Optional["PersonalTradeQueryService"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
    ) -> None:
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._conversation_command_service = conversation_command_service
        self._skill_loadout_repository = skill_loadout_repository
        self._game_time_provider = game_time_provider
        self._quest_repository = quest_repository
        self._guild_repository = guild_repository
        self._shop_repository = shop_repository
        self._personal_trade_query_service = personal_trade_query_service
        self._player_profile_repository = player_profile_repository

    def build_inventory_items(self, player_id: PlayerId) -> List[InventoryItemDto]:
        if self._player_inventory_repository is None or self._item_repository is None:
            return []
        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            return []

        items: List[InventoryItemDto] = []
        for slot_index in range(inventory.max_slots):
            item_id = inventory.get_item_instance_id_by_slot(SlotId(slot_index))
            if item_id is None:
                continue
            item = self._item_repository.find_by_id(item_id)
            if item is None:
                continue
            items.append(
                InventoryItemDto(
                    inventory_slot_id=slot_index,
                    item_instance_id=item.item_instance_id.value,
                    display_name=item.item_spec.name,
                    quantity=item.quantity,
                    is_placeable=item.item_spec.is_placeable_item(),
                )
            )
        return items

    def build_chest_items(
        self,
        physical_map,
        visible_objects: List[VisibleObjectDto],
    ) -> List[ChestItemDto]:
        if self._item_repository is None:
            return []
        items: List[ChestItemDto] = []
        for obj in visible_objects:
            if obj.object_kind != "chest" or not obj.can_take_from_chest:
                continue
            try:
                chest = physical_map.get_object(WorldObjectId.create(obj.object_id))
            except (ObjectNotFoundException, WorldObjectIdValidationException):
                continue
            component = chest.component
            if not isinstance(component, ChestComponent):
                continue
            item_ids = component.item_ids
            for item_id in item_ids:
                item = self._item_repository.find_by_id(item_id)
                if item is None:
                    continue
                items.append(
                    ChestItemDto(
                        chest_world_object_id=obj.object_id,
                        chest_display_name=obj.display_name or "宝箱",
                        item_instance_id=item.item_instance_id.value,
                        display_name=item.item_spec.name,
                        quantity=item.quantity,
                    )
                )
        return items

    def build_active_conversation(
        self,
        player_id: int,
        visible_objects: List[VisibleObjectDto],
    ) -> Optional[ActiveConversationDto]:
        if self._conversation_command_service is None:
            return None
        from ai_rpg_world.application.conversation.contracts.commands import (
            GetCurrentNodeQuery,
        )

        for obj in visible_objects:
            if obj.object_kind != "npc":
                continue
            session = self._conversation_command_service.get_current_node(
                GetCurrentNodeQuery(player_id=player_id, npc_id_value=obj.object_id)
            )
            if session is None:
                continue
            choices: List[ConversationChoiceDto] = [
                ConversationChoiceDto(display_text=text, choice_index=index)
                for index, (text, _next_id) in enumerate(session.current_node.choices)
            ]
            if session.current_node.has_next and not session.current_node.choices:
                choices.append(ConversationChoiceDto(display_text="次へ", is_next=True))
            return ActiveConversationDto(
                npc_world_object_id=obj.object_id,
                npc_display_name=obj.display_name or "NPC",
                node_text=session.current_node.text,
                choices=choices,
                is_terminal=session.current_node.is_terminal,
                dialogue_tree_id_value=getattr(session, "dialogue_tree_id_value", None),
            )
        return None

    def build_active_quest_ids(self, player_id: int) -> List[int]:
        """受託中クエストの ID 一覧を返す（scope_keys 用）"""
        if self._quest_repository is None:
            return []
        quests = self._quest_repository.find_accepted_quests_by_player(PlayerId(player_id))
        return [int(q.quest_id.value) for q in quests]

    def build_guild_ids(self, player_id: int) -> List[int]:
        """プレイヤーが所属するギルドの ID 一覧を返す（scope_keys 用）"""
        if self._guild_repository is None:
            return []
        guilds = self._guild_repository.find_guilds_by_player_id(PlayerId(player_id))
        return [int(g.guild_id.value) for g in guilds]

    def build_nearby_shop_ids(
        self, spot_id: int, location_area_ids: Optional[List[int]] = None
    ) -> List[int]:
        """現在地スポットのショップ ID 一覧を返す（scope_keys 用）。複数ロケーション対応。"""
        if self._shop_repository is None or not location_area_ids:
            return []
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId

        seen: set[int] = set()
        result: List[int] = []
        for area_id in location_area_ids:
            shop = self._shop_repository.find_by_spot_and_location(
                SpotId(spot_id), LocationAreaId(area_id)
            )
            if shop is not None:
                sid = int(shop.shop_id.value)
                if sid not in seen:
                    seen.add(sid)
                    result.append(sid)
        return result

    def build_active_quests(self, player_id: int) -> List[ActiveQuestSummaryDto]:
        """受託中クエストのサマリ一覧（LLM readable）"""
        if self._quest_repository is None:
            return []
        quests = self._quest_repository.find_accepted_quests_by_player(PlayerId(player_id))
        result: List[ActiveQuestSummaryDto] = []
        for q in quests:
            total = len(q.objectives)
            completed = sum(1 for obj in q.objectives if obj.is_completed())
            summary_text = f"目標 {completed}/{total} 達成"
            result.append(
                ActiveQuestSummaryDto(
                    quest_id=int(q.quest_id.value),
                    summary_text=summary_text,
                    objectives_completed=completed,
                    objectives_total=total,
                )
            )
        return result

    def build_guild_memberships(
        self, player_id: int, player_area_ids: Optional[List[int]] = None
    ) -> List[GuildMembershipSummaryDto]:
        """所属ギルドのサマリ一覧（LLM readable）。player_area_ids のいずれかがギルドの LocationArea と一致する場合 description を設定。"""
        if self._guild_repository is None:
            return []
        from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole

        guilds = self._guild_repository.find_guilds_by_player_id(PlayerId(player_id))
        result: List[GuildMembershipSummaryDto] = []
        for g in guilds:
            membership = g.get_member(PlayerId(player_id))
            if membership is not None:
                desc: Optional[str] = None
                if player_area_ids and g.location_area_id.value in player_area_ids:
                    desc = g.description
                members_list: Optional[List[GuildMemberSummaryDto]] = None
                if membership.role in (GuildRole.LEADER, GuildRole.OFFICER):
                    members_list = []
                    for pid, m in g.members.items():
                        player_name_str = f"プレイヤー{int(pid)}"
                        if self._player_profile_repository is not None:
                            profile = self._player_profile_repository.find_by_id(pid)
                            if profile is not None:
                                player_name_str = profile.name.value
                        members_list.append(
                            GuildMemberSummaryDto(
                                player_id=int(pid),
                                player_name=player_name_str,
                                role=m.role.value,
                            )
                        )
                result.append(
                    GuildMembershipSummaryDto(
                        guild_id=int(g.guild_id.value),
                        guild_name=g.name,
                        role=membership.role.value,
                        description=desc,
                        members=members_list,
                    )
                )
        return result

    def build_nearby_shops(
        self, spot_id: int, location_area_ids: Optional[List[int]] = None
    ) -> List[NearbyShopSummaryDto]:
        """現在地のショップサマリ一覧（LLM readable）。複数ロケーション対応。出品一覧も含み listing_label 解決に使う。"""
        if self._shop_repository is None or not location_area_ids:
            return []
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId

        seen_shop_ids: set[int] = set()
        result: List[NearbyShopSummaryDto] = []
        for area_id in location_area_ids:
            shop = self._shop_repository.find_by_spot_and_location(
                SpotId(spot_id), LocationAreaId(area_id)
            )
            if shop is None:
                continue
            sid = int(shop.shop_id.value)
            if sid in seen_shop_ids:
                continue
            seen_shop_ids.add(sid)
            listings_dto: List[ShopListingSummaryDto] = []
            for listing_id, listing in shop.listings.items():
                item_name = "不明"
                if self._item_repository is not None:
                    item = self._item_repository.find_by_id(listing.item_instance_id)
                    if item is not None:
                        item_name = item.item_spec.name
                listings_dto.append(
                    ShopListingSummaryDto(
                        listing_id=listing_id.value,
                        item_name=item_name,
                        price_per_unit=listing.price_per_unit.value,
                    )
                )
            result.append(
                NearbyShopSummaryDto(
                    shop_id=sid,
                    shop_name=shop.name,
                    listing_count=len(listings_dto),
                    listings=listings_dto,
                    description=shop.description or None,
                )
            )
        return result

    def build_available_trades(self, player_id: int, limit: int = 5) -> List[AvailableTradeSummaryDto]:
        """プレイヤー宛の取引サマリ一覧（LLM readable）"""
        if self._personal_trade_query_service is None:
            return []
        try:
            trade_list = self._personal_trade_query_service.get_personal_trades(
                player_id, limit=limit
            )
            return [
                AvailableTradeSummaryDto(
                    trade_id=int(listing.trade_id),
                    item_name=listing.item_name or "不明",
                    requested_gold=listing.requested_gold,
                )
                for listing in trade_list.listings
            ]
        except PersonalTradeQueryApplicationException:
            return []

    def build_usable_skills(self, player_id: int) -> List[UsableSkillDto]:
        if self._skill_loadout_repository is None or self._game_time_provider is None:
            return []
        loadout = self._skill_loadout_repository.find_by_owner_id(player_id)
        if loadout is None:
            return []
        current_tick = self._game_time_provider.get_current_tick().value
        deck = loadout.get_current_deck(current_tick)
        skills: List[UsableSkillDto] = []
        for slot_index, skill in enumerate(deck.slots):
            if skill is None or not loadout.can_use_skill(slot_index, current_tick):
                continue
            skills.append(
                UsableSkillDto(
                    skill_loadout_id=loadout.loadout_id.value,
                    skill_slot_index=slot_index,
                    skill_id=skill.skill_id.value,
                    display_name=skill.name,
                    mp_cost=skill.mp_cost or 0,
                    stamina_cost=skill.stamina_cost or 0,
                    hp_cost=skill.hp_cost or 0,
                )
            )
        return skills

    def build_attention_level_options(self) -> List[AttentionLevelOptionDto]:
        return [
            AttentionLevelOptionDto(
                value=AttentionLevel.FULL.value,
                display_name="フル",
                description="すべての観測を受け取ります。",
            ),
            AttentionLevelOptionDto(
                value=AttentionLevel.FILTER_SOCIAL.value,
                display_name="会話重視",
                description="社会的な観測を要約します。",
            ),
            AttentionLevelOptionDto(
                value=AttentionLevel.IGNORE.value,
                display_name="最小",
                description="直接関係する観測を優先します。",
            ),
        ]

    def can_destroy_placeable(self, physical_map, player_id: int) -> bool:
        try:
            actor = physical_map.get_actor(WorldObjectId.create(player_id))
        except (
            ObjectNotFoundException,
            NotAnActorException,
            WorldObjectIdValidationException,
        ):
            return False
        front_coord = actor.coordinate.neighbor(actor.direction)
        for obj in physical_map.get_objects_at(front_coord):
            component = obj.component
            if isinstance(component, PlaceableComponent):
                return True
        return False

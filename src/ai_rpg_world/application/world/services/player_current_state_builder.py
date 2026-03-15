"""プレイヤー現在状態の read model を組み立てるビルダー。"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import (
    ActiveHarvestDto,
    ActiveConversationDto,
    AvailableLocationAreaDto,
    AttentionLevelOptionDto,
    ChestItemDto,
    ConversationChoiceDto,
    PlayerCurrentStateDto,
    PlayerMovementOptionsDto,
    UsableSkillDto,
    VisibleObjectDto,
    InventoryItemDto,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.visible_object_read_model_builder import (
    VisibleObjectReadModelBuilder,
)
from ai_rpg_world.application.world.services.visible_tile_map_builder import (
    VisibleTileMapBuilder,
)
from ai_rpg_world.application.world.services.player_runtime_context_builder import (
    PlayerRuntimeContextBuilder,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    NotAnActorException,
    ObjectNotFoundException,
    TileNotFoundException,
    WorldObjectIdValidationException,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import (
    ITransitionPolicyRepository,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent

from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort

if TYPE_CHECKING:
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.application.world.services.transition_condition_evaluator import (
        TransitionConditionEvaluator,
    )
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
        PlayerStatusAggregate,
    )
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
    from ai_rpg_world.application.trade.services.personal_trade_query_service import (
        PersonalTradeQueryService,
    )
    from ai_rpg_world.domain.skill.repository.skill_repository import (
        SkillDeckProgressRepository,
        SkillLoadoutRepository,
    )
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
        PhysicalMapAggregate,
    )
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.world.entity.spot import Spot
    from ai_rpg_world.domain.world.service.world_time_config_service import (
        WorldTimeConfigService,
    )


class PlayerCurrentStateBuilder:
    """PlayerCurrentStateDto の組み立てを担う（視界オブジェクトは build_visible_objects で構築）。"""

    def __init__(
        self,
        player_status_repository: "PlayerStatusRepository",
        player_profile_repository: "PlayerProfileRepository",
        spot_repository: "SpotRepository",
        connected_spots_provider: IConnectedSpotsProvider,
        monster_repository: Optional["MonsterRepository"] = None,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional["TransitionConditionEvaluator"] = None,
        player_inventory_repository: Optional["PlayerInventoryRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        conversation_command_service: Optional["ConversationCommandService"] = None,
        skill_loadout_repository: Optional["SkillLoadoutRepository"] = None,
        skill_deck_progress_repository: Optional["SkillDeckProgressRepository"] = None,
        game_time_provider: Optional["GameTimeProvider"] = None,
        world_time_config_service: Optional["WorldTimeConfigService"] = None,
        quest_repository: Optional["QuestRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        personal_trade_query_service: Optional["PersonalTradeQueryService"] = None,
        player_audience_query: Optional[IPlayerAudienceQueryPort] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._spot_repository = spot_repository
        self._connected_spots_provider = connected_spots_provider
        self._monster_repository = monster_repository
        self._transition_policy_repository = transition_policy_repository
        self._transition_condition_evaluator = transition_condition_evaluator
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._conversation_command_service = conversation_command_service
        self._skill_loadout_repository = skill_loadout_repository
        self._game_time_provider = game_time_provider
        self._world_time_config_service = world_time_config_service
        self._guild_repository = guild_repository
        self._shop_repository = shop_repository
        self._personal_trade_query_service = personal_trade_query_service
        self._player_audience_query = player_audience_query
        self._visible_object_builder = VisibleObjectReadModelBuilder(
            player_profile_repository=player_profile_repository,
            monster_repository=monster_repository,
        )
        self._visible_tile_map_builder = VisibleTileMapBuilder()
        self._runtime_context_builder = PlayerRuntimeContextBuilder(
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

    def build_player_current_state(
        self,
        *,
        query: GetPlayerCurrentStateQuery,
        player_status: "PlayerStatusAggregate",
        player_name: str,
        spot: "Spot",
        physical_map: "PhysicalMapAggregate",
        available_moves_result: Optional[PlayerMovementOptionsDto],
    ) -> PlayerCurrentStateDto:
        """
        PlayerCurrentStateDto を組み立てる。

        境界:
        - 現在状態 (current state): 位置・天気・地形・同スポット人数・接続先
        - ツール/runtime context: 視界オブジェクト・利用可能移動先・インベントリ・ショップ・取引等
        - memory retrieval hints: active_quest_ids, guild_ids, nearby_shop_ids（関係性メモリ検索用）
        """
        player_id = player_status.player_id
        coord = player_status.current_coordinate
        if coord is None:
            raise ValueError("player_status.current_coordinate must not be None")

        areas = physical_map.get_location_areas_at(coord)
        area_ids = [int(la.location_id) for la in areas]
        area_names = [la.name for la in areas]
        area_id = area_ids[0] if area_ids else None
        area_name = area_names[0] if area_names else None
        area_description = areas[0].description if areas else None

        if self._player_audience_query is not None:
            player_ids_at_spot = self._player_audience_query.players_at_spot(
                player_status.current_spot_id
            )
            current_player_ids = {int(p.value) for p in player_ids_at_spot}
        else:
            current_player_ids = {
                int(s.player_id)
                for s in self._player_status_repository.find_all()
                if s.current_spot_id == player_status.current_spot_id
            }
        connected_spot_ids = set()
        connected_spot_names = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(
            player_status.current_spot_id
        ):
            connected_spot_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot is not None:
                connected_spot_names.add(conn_spot.name)

        weather_state = (
            physical_map.weather_state
            if physical_map.weather_state
            else WeatherState(WeatherTypeEnum.CLEAR, 0.0)
        )
        # 座標がマップ範囲外（TileNotFoundException）の場合は地形タイプを None のままとする。
        # 他フィールドは引き続き有効。LLM コンテキストでは部分的欠損は許容する。
        current_terrain_type = None
        try:
            tile = physical_map.get_tile(coord)
            current_terrain_type = tile.terrain_type.type.value
        except TileNotFoundException:
            pass

        distance = max(0, query.view_distance)
        visible_objects = self.build_visible_objects(
            physical_map=physical_map,
            origin=coord,
            distance=distance,
            player_id=player_id,
        )
        actionable_objects = self._visible_object_builder.build_actionable_objects(
            visible_objects
        )
        notable_objects = self._visible_object_builder.build_notable_objects(
            visible_objects
        )

        actor = self._get_player_actor(physical_map, player_id)
        current_tick_value = (
            self._game_time_provider.get_current_tick().value
            if self._game_time_provider is not None
            else 0
        )
        busy_until_tick = (
            actor.busy_until.value
            if actor is not None and actor.busy_until is not None
            else None
        )
        is_busy = busy_until_tick is not None and busy_until_tick > current_tick_value
        has_active_path = bool(player_status.planned_path)
        active_harvest = self._build_active_harvest(
            physical_map=physical_map,
            player_id=player_id,
            visible_objects=visible_objects,
        )

        available_moves = (
            available_moves_result.available_moves if available_moves_result else None
        )
        total_available_moves = (
            available_moves_result.total_available_moves
            if available_moves_result
            else None
        )

        available_location_areas = [
            AvailableLocationAreaDto(
                location_area_id=int(la.location_id),
                name=la.name,
            )
            for la in physical_map.get_all_location_areas()
            if la.is_active
        ] or None

        # 視界タイルマップ（include_tile_map=True のときのみ）
        visible_tile_map = None
        if query.include_tile_map:
            visible_tile_map = self._visible_tile_map_builder.build_visible_tile_map(
                physical_map=physical_map,
                origin=coord,
                view_distance=distance,
                visible_objects=visible_objects,
                player_id=int(player_id),
            )

        # ゲーム内現在時刻ラベル（game_time_provider と world_time_config が揃っているときのみ）
        current_game_time_label = None
        if (
            self._game_time_provider is not None
            and self._world_time_config_service is not None
        ):
            from ai_rpg_world.domain.world.value_object.game_date_time import (
                game_date_time_from_tick,
            )
            tick = self._game_time_provider.get_current_tick().value
            game_dt = game_date_time_from_tick(
                tick,
                self._world_time_config_service.get_ticks_per_day(),
                self._world_time_config_service.get_days_per_month(),
                self._world_time_config_service.get_months_per_year(),
            )
            current_game_time_label = game_dt.format_for_display()

        # 境界: ツール/runtime context（LLM prompt 上のラベル解決・利用可否判定に利用）
        # - available_moves, visible_objects, actionable/notable
        # - inventory_items, chest_items, nearby_shops, available_trades
        # - memory retrieval hints: active_quest_ids, guild_ids, nearby_shop_ids
        return PlayerCurrentStateDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(player_status.current_spot_id),
            current_spot_name=spot.name,
            current_spot_description=spot.description,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            area_ids=area_ids,
            area_names=area_names,
            area_id=area_id,
            area_name=area_name,
            current_location_description=area_description,
            current_player_count=len(current_player_ids),
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names,
            weather_type=weather_state.weather_type.value,
            weather_intensity=weather_state.intensity,
            current_game_time_label=current_game_time_label,
            current_terrain_type=current_terrain_type,
            visible_objects=visible_objects,
            view_distance=distance,
            visible_tile_map=visible_tile_map,
            available_moves=available_moves,
            total_available_moves=total_available_moves,
            available_location_areas=available_location_areas,
            attention_level=player_status.attention_level,
            is_busy=is_busy,
            busy_until_tick=busy_until_tick,
            has_active_path=has_active_path,
            inventory_items=self._runtime_context_builder.build_inventory_items(player_id),
            chest_items=self._runtime_context_builder.build_chest_items(physical_map, visible_objects),
            active_conversation=self._runtime_context_builder.build_active_conversation(
                query.player_id, visible_objects
            ),
            active_harvest=active_harvest,
            active_quest_ids=self._runtime_context_builder.build_active_quest_ids(query.player_id),
            guild_ids=self._runtime_context_builder.build_guild_ids(query.player_id),
            nearby_shop_ids=self._runtime_context_builder.build_nearby_shop_ids(
                int(player_status.current_spot_id), area_ids
            ),
            active_quests=self._runtime_context_builder.build_active_quests(query.player_id),
            guild_memberships=self._runtime_context_builder.build_guild_memberships(
                query.player_id, area_ids
            ),
            nearby_shops=self._runtime_context_builder.build_nearby_shops(
                int(player_status.current_spot_id), area_ids
            ),
            available_trades=self._runtime_context_builder.build_available_trades(query.player_id),
            usable_skills=self._runtime_context_builder.build_usable_skills(query.player_id),
            equipable_skill_candidates=self._runtime_context_builder.build_equipable_skill_candidates(
                query.player_id
            ),
            skill_equip_slots=self._runtime_context_builder.build_skill_equip_slots(
                query.player_id
            ),
            pending_skill_proposals=self._runtime_context_builder.build_pending_skill_proposals(
                query.player_id
            ),
            awakened_action=self._runtime_context_builder.build_awakened_action(
                query.player_id
            ),
            attention_level_options=self._runtime_context_builder.build_attention_level_options(),
            can_destroy_placeable=self._runtime_context_builder.can_destroy_placeable(
                physical_map, query.player_id
            ),
            actionable_objects=actionable_objects,
            notable_objects=notable_objects,
        )

    def build_visible_objects(
        self,
        *,
        physical_map: "PhysicalMapAggregate",
        origin: Coordinate,
        distance: int,
        player_id: PlayerId,
    ) -> List[VisibleObjectDto]:
        return self._visible_object_builder.build_visible_objects(
            physical_map=physical_map,
            origin=origin,
            distance=distance,
            player_id=player_id,
        )

    def _build_active_harvest(
        self,
        *,
        physical_map: "PhysicalMapAggregate",
        player_id: PlayerId,
        visible_objects: List[VisibleObjectDto],
    ) -> Optional[ActiveHarvestDto]:
        actor_object_id = WorldObjectId.create(int(player_id))
        visible_names = {obj.object_id: (obj.display_name or obj.object_type) for obj in visible_objects}
        for obj in physical_map.get_all_objects():
            if not isinstance(obj.component, HarvestableComponent):
                continue
            if obj.component.current_actor_id != actor_object_id:
                continue
            finish_tick = obj.component.harvest_finish_tick
            if finish_tick is None:
                continue
            return ActiveHarvestDto(
                target_world_object_id=int(obj.object_id),
                target_display_name=visible_names.get(obj.object_id.value, obj.object_type.value),
                finish_tick=finish_tick.value,
            )
        return None

    def _get_player_actor(self, physical_map, player_id: PlayerId):
        """プレイヤーアクターを取得。存在しない・不正な場合は None を返す。"""
        try:
            from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

            return physical_map.get_actor(WorldObjectId.create(int(player_id)))
        except (
            ObjectNotFoundException,
            NotAnActorException,
            WorldObjectIdValidationException,
        ):
            return None

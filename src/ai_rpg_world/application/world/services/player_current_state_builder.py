"""プレイヤー現在状態の read model を組み立てるビルダー。"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    AttentionLevelOptionDto,
    ChestItemDto,
    ConversationChoiceDto,
    PlayerCurrentStateDto,
    PlayerMovementOptionsDto,
    UsableSkillDto,
    VisibleContextDto,
    VisibleObjectDto,
    InventoryItemDto,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.visible_object_read_model_builder import (
    VisibleObjectReadModelBuilder,
)
from ai_rpg_world.application.world.services.player_supplemental_context_builder import (
    PlayerSupplementalContextBuilder,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import TileNotFoundException
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import (
    ITransitionPolicyRepository,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState

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
    from ai_rpg_world.domain.skill.repository.skill_repository import (
        SkillLoadoutRepository,
    )
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
        PhysicalMapAggregate,
    )
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.world.entity.spot import Spot


class PlayerCurrentStateBuilder:
    """PlayerCurrentStateDto と VisibleContextDto の組み立てを担う。"""

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
        game_time_provider: Optional["GameTimeProvider"] = None,
        quest_repository: Optional["QuestRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
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
        self._guild_repository = guild_repository
        self._shop_repository = shop_repository
        self._visible_object_builder = VisibleObjectReadModelBuilder(
            player_profile_repository=player_profile_repository,
            monster_repository=monster_repository,
        )
        self._supplemental_context_builder = PlayerSupplementalContextBuilder(
            player_inventory_repository=player_inventory_repository,
            item_repository=item_repository,
            conversation_command_service=conversation_command_service,
            skill_loadout_repository=skill_loadout_repository,
            game_time_provider=game_time_provider,
            quest_repository=quest_repository,
            guild_repository=guild_repository,
            shop_repository=shop_repository,
        )

    def build_visible_context(
        self,
        *,
        player_id: int,
        player_name: str,
        spot: "Spot",
        physical_map: "PhysicalMapAggregate",
        origin: Coordinate,
        view_distance: int,
    ) -> VisibleContextDto:
        player_id_vo = PlayerId(player_id)
        visible_objects = self.build_visible_objects(
            physical_map=physical_map,
            origin=origin,
            distance=view_distance,
            player_id=player_id_vo,
        )
        return VisibleContextDto(
            player_id=player_id,
            player_name=player_name,
            spot_id=int(spot.spot_id),
            spot_name=spot.name,
            center_x=origin.x,
            center_y=origin.y,
            center_z=origin.z,
            view_distance=view_distance,
            visible_objects=visible_objects,
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
        player_id = player_status.player_id
        coord = player_status.current_coordinate
        if coord is None:
            raise ValueError("player_status.current_coordinate must not be None")

        area_id = None
        area_name = None
        areas = physical_map.get_location_areas_at(coord)
        if areas:
            area_id = int(areas[0].location_id)
            area_name = areas[0].name

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

        available_moves = (
            available_moves_result.available_moves if available_moves_result else None
        )
        total_available_moves = (
            available_moves_result.total_available_moves
            if available_moves_result
            else None
        )

        return PlayerCurrentStateDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(player_status.current_spot_id),
            current_spot_name=spot.name,
            current_spot_description=spot.description,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            area_id=area_id,
            area_name=area_name,
            current_player_count=len(current_player_ids),
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names,
            weather_type=weather_state.weather_type.value,
            weather_intensity=weather_state.intensity,
            current_terrain_type=current_terrain_type,
            visible_objects=visible_objects,
            view_distance=distance,
            available_moves=available_moves,
            total_available_moves=total_available_moves,
            attention_level=player_status.attention_level,
            is_busy=is_busy,
            busy_until_tick=busy_until_tick,
            has_active_path=has_active_path,
            inventory_items=self._supplemental_context_builder.build_inventory_items(player_id),
            chest_items=self._supplemental_context_builder.build_chest_items(physical_map, visible_objects),
            active_conversation=self._supplemental_context_builder.build_active_conversation(
                query.player_id, visible_objects
            ),
            active_quest_ids=self._supplemental_context_builder.build_active_quest_ids(query.player_id),
            guild_ids=self._supplemental_context_builder.build_guild_ids(query.player_id),
            nearby_shop_ids=self._supplemental_context_builder.build_nearby_shop_ids(
                int(player_status.current_spot_id), area_id
            ),
            usable_skills=self._supplemental_context_builder.build_usable_skills(query.player_id),
            attention_level_options=self._supplemental_context_builder.build_attention_level_options(),
            can_destroy_placeable=self._supplemental_context_builder.can_destroy_placeable(
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

    def _get_player_actor(self, physical_map, player_id: PlayerId):
        try:
            from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

            return physical_map.get_actor(WorldObjectId.create(int(player_id)))
        except Exception:
            return None

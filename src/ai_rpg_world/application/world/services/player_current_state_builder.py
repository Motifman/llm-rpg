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
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.entity.world_object_component import PlaceableComponent
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import TileNotFoundException
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import (
    ITransitionPolicyRepository,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.application.world.services.transition_condition_evaluator import (
        TransitionConditionEvaluator,
    )
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
            inventory_items=self._build_inventory_items(player_id),
            chest_items=self._build_chest_items(physical_map, visible_objects),
            active_conversation=self._build_active_conversation(
                query.player_id, visible_objects
            ),
            usable_skills=self._build_usable_skills(query.player_id),
            attention_level_options=self._build_attention_level_options(),
            can_destroy_placeable=self._can_destroy_placeable(
                physical_map, query.player_id
            ),
        )

    def build_visible_objects(
        self,
        *,
        physical_map: "PhysicalMapAggregate",
        origin: Coordinate,
        distance: int,
        player_id: PlayerId,
    ) -> List[VisibleObjectDto]:
        objects_in_range = physical_map.get_objects_in_range(origin, distance)
        visible_objects: List[VisibleObjectDto] = []
        for obj in objects_in_range:
            if obj.coordinate != origin and not physical_map.is_visible(
                origin, obj.coordinate
            ):
                continue
            visible_objects.append(
                self._build_visible_object_dto(
                    obj=obj,
                    origin=origin,
                    player_id=player_id,
                )
            )
        return visible_objects

    def _build_visible_object_dto(
        self,
        *,
        obj,
        origin: Coordinate,
        player_id: PlayerId,
    ) -> VisibleObjectDto:
        can_interact = self._can_interact(origin, obj)
        can_harvest = self._can_harvest(origin, obj)
        can_store_in_chest = self._can_store_in_chest(origin, obj)
        can_take_from_chest = self._can_take_from_chest(origin, obj)
        available_interactions = self._build_available_interaction_labels(
            can_interact=can_interact,
            can_harvest=can_harvest,
            can_store_in_chest=can_store_in_chest,
            can_take_from_chest=can_take_from_chest,
        )
        return VisibleObjectDto(
            object_id=obj.object_id.value,
            object_type=obj.object_type.value,
            x=obj.coordinate.x,
            y=obj.coordinate.y,
            z=obj.coordinate.z,
            distance=origin.distance_to(obj.coordinate),
            display_name=self._visible_object_display_name(obj),
            object_kind=self._visible_object_kind(obj),
            direction_from_player=self._direction_from_to(origin, obj.coordinate),
            is_interactable=obj.interaction_type is not None,
            player_id_value=int(obj.player_id) if obj.player_id is not None else None,
            is_self=obj.player_id == player_id,
            interaction_type=self._visible_object_interaction_type(obj),
            available_interactions=available_interactions,
            can_interact=can_interact,
            can_harvest=can_harvest,
            can_store_in_chest=can_store_in_chest,
            can_take_from_chest=can_take_from_chest,
        )

    def _build_available_interaction_labels(
        self,
        *,
        can_interact: bool,
        can_harvest: bool,
        can_store_in_chest: bool,
        can_take_from_chest: bool,
    ) -> List[str]:
        actions: List[str] = []
        if can_harvest:
            actions.append("harvest")
        if can_interact:
            actions.append("interact")
        if can_store_in_chest:
            actions.append("store_in_chest")
        if can_take_from_chest:
            actions.append("take_from_chest")
        return actions

    def _direction_from_to(self, origin: Coordinate, target: Coordinate) -> str:
        dx = target.x - origin.x
        dy = target.y - origin.y
        if dx == 0 and dy == 0:
            return "ここ"
        vertical = ""
        horizontal = ""
        if dy < 0:
            vertical = "北"
        elif dy > 0:
            vertical = "南"
        if dx > 0:
            horizontal = "東"
        elif dx < 0:
            horizontal = "西"
        return vertical + horizontal or "ここ"

    def _visible_object_display_name(self, obj) -> str:
        if obj.object_type == ObjectTypeEnum.PLAYER and obj.player_id is not None:
            profile = self._player_profile_repository.find_by_id(obj.player_id)
            if profile is not None:
                return profile.name.value
            return "不明なプレイヤー"
        if obj.object_type == ObjectTypeEnum.NPC:
            if self._monster_repository is not None:
                monster = self._monster_repository.find_by_world_object_id(obj.object_id)
                if monster is not None:
                    return monster.template.name
            return "誰か"
        name_by_type = {
            ObjectTypeEnum.CHEST: "宝箱",
            ObjectTypeEnum.DOOR: "ドア",
            ObjectTypeEnum.GATE: "門",
            ObjectTypeEnum.SIGN: "看板",
            ObjectTypeEnum.SWITCH: "スイッチ",
            ObjectTypeEnum.RESOURCE: "資源",
            ObjectTypeEnum.GROUND_ITEM: "落ちているアイテム",
        }
        return name_by_type.get(obj.object_type, obj.object_type.value)

    def _visible_object_kind(self, obj) -> str:
        if obj.object_type == ObjectTypeEnum.PLAYER:
            return "player"
        if obj.object_type == ObjectTypeEnum.NPC:
            if getattr(obj, "interaction_type", None) is not None:
                return "npc"
            return "monster"
        if obj.object_type == ObjectTypeEnum.CHEST:
            return "chest"
        if obj.object_type == ObjectTypeEnum.DOOR:
            return "door"
        if obj.object_type == ObjectTypeEnum.RESOURCE:
            return "resource"
        if obj.object_type == ObjectTypeEnum.GROUND_ITEM:
            return "ground_item"
        return "object"

    def _visible_object_interaction_type(self, obj) -> Optional[str]:
        interaction_type = getattr(obj, "interaction_type", None)
        if interaction_type is None:
            return None
        return interaction_type.value

    def _is_in_action_range(self, origin: Coordinate, obj) -> bool:
        return origin.chebyshev_distance_to(obj.coordinate) <= 1

    def _can_interact(self, origin: Coordinate, obj) -> bool:
        return getattr(obj, "interaction_type", None) is not None and self._is_in_action_range(
            origin, obj
        )

    def _can_harvest(self, origin: Coordinate, obj) -> bool:
        return obj.object_type == ObjectTypeEnum.RESOURCE and self._is_in_action_range(
            origin, obj
        )

    def _can_store_in_chest(self, origin: Coordinate, obj) -> bool:
        if obj.object_type != ObjectTypeEnum.CHEST or not self._is_in_action_range(origin, obj):
            return False
        interaction_data = getattr(obj, "interaction_data", {}) or {}
        return bool(interaction_data.get("is_open"))

    def _can_take_from_chest(self, origin: Coordinate, obj) -> bool:
        return self._can_store_in_chest(origin, obj)

    def _get_player_actor(self, physical_map, player_id: PlayerId):
        try:
            return physical_map.get_actor(WorldObjectId.create(int(player_id)))
        except Exception:
            return None

    def _build_inventory_items(self, player_id: PlayerId) -> List[InventoryItemDto]:
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

    def _build_chest_items(
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
            except Exception:
                continue
            component = getattr(chest, "component", None)
            item_ids = getattr(component, "item_ids", [])
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

    def _build_active_conversation(
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
            )
        return None

    def _build_usable_skills(self, player_id: int) -> List[UsableSkillDto]:
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

    def _build_attention_level_options(self) -> List[AttentionLevelOptionDto]:
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

    def _can_destroy_placeable(self, physical_map, player_id: int) -> bool:
        try:
            actor = physical_map.get_actor(WorldObjectId.create(player_id))
        except Exception:
            return False
        front_coord = actor.coordinate.neighbor(actor.direction)
        for obj in physical_map.get_objects_at(front_coord):
            component = getattr(obj, "component", None)
            if isinstance(component, PlaceableComponent):
                return True
        return False

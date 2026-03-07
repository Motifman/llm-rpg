"""ワールドクエリサービス（読み取り専用の位置情報等）"""

import logging
from typing import Optional, Callable, Any, List, TYPE_CHECKING

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerLocationQuery,
    GetSpotContextForPlayerQuery,
    GetVisibleContextQuery,
    GetAvailableMovesQuery,
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    AttentionLevelOptionDto,
    PlayerLocationDto,
    SpotInfoDto,
    VisibleContextDto,
    VisibleObjectDto,
    PlayerMovementOptionsDto,
    AvailableMoveDto,
    ChestItemDto,
    ConversationChoiceDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
    UsableSkillDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import TileNotFoundException
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object_component import PlaceableComponent
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
)
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
    MapNotFoundException,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
    from ai_rpg_world.application.conversation.services.conversation_command_service import (
        ConversationCommandService,
    )
    from ai_rpg_world.domain.monster.repository.monster_repository import (
        MonsterRepository,
    )
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.player.repository.player_inventory_repository import (
        PlayerInventoryRepository,
    )
    from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository


class WorldQueryService:
    """ワールドに関する読み取り専用クエリを提供するサービス"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        monster_repository: Optional["MonsterRepository"] = None,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
        player_inventory_repository: Optional["PlayerInventoryRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        conversation_command_service: Optional["ConversationCommandService"] = None,
        skill_loadout_repository: Optional["SkillLoadoutRepository"] = None,
        game_time_provider: Optional["GameTimeProvider"] = None,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
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
        self._logger = logging.getLogger(self.__class__.__name__)

    def _direction_from_to(self, origin, target) -> str:
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

    def _visible_object_available_interactions(self, obj) -> List[str]:
        actions: List[str] = []
        if obj.object_type == ObjectTypeEnum.RESOURCE:
            actions.append("harvest")
        if getattr(obj, "interaction_type", None) is not None:
            actions.append("interact")
        if obj.object_type == ObjectTypeEnum.CHEST:
            interaction_data = getattr(obj, "interaction_data", {}) or {}
            if interaction_data.get("is_open"):
                actions.extend(["store_in_chest", "take_from_chest"])
        return actions

    def _build_inventory_items(
        self,
        player_id: PlayerId,
    ) -> List[InventoryItemDto]:
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
            if obj.object_kind != "chest" or "take_from_chest" not in obj.available_interactions:
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
        from ai_rpg_world.application.conversation.contracts.commands import GetCurrentNodeQuery

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

    def _build_usable_skills(
        self,
        player_id: int,
    ) -> List[UsableSkillDto]:
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

    def _can_destroy_placeable(
        self,
        physical_map,
        player_id: int,
    ) -> bool:
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

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise MovementCommandException(str(e), player_id=context.get("player_id"))
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def get_player_location(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得。未配置の場合は None、プレイヤー／スポット不在時は例外。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_player_location_impl(query),
            context={"action": "get_player_location", "player_id": query.player_id},
        )

    def _get_player_location_impl(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得する実装。未配置時は None を返す。"""
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)
        player_name = profile.name.value

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))
        spot_name = spot.name
        spot_desc = spot.description

        area_id = None
        area_name = None
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
            if areas:
                area_id = int(areas[0].location_id)
                area_name = areas[0].name

        return PlayerLocationDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(spot_id),
            current_spot_name=spot_name,
            current_spot_description=spot_desc,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            area_id=area_id,
            area_name=area_name,
        )

    def get_spot_context_for_player(
        self, query: GetSpotContextForPlayerQuery
    ) -> Optional[SpotInfoDto]:
        """プレイヤーの現在スポット情報＋接続先一覧を取得。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_spot_context_for_player_impl(query),
            context={"action": "get_spot_context_for_player", "player_id": query.player_id},
        )

    def _get_spot_context_for_player_impl(
        self, query: GetSpotContextForPlayerQuery
    ) -> Optional[SpotInfoDto]:
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        area_id = None
        area_name = None
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
            if areas:
                area_id = int(areas[0].location_id)
                area_name = areas[0].name

        current_player_ids: set = set()
        all_statuses = self._player_status_repository.find_all()
        for s in all_statuses:
            if s.current_spot_id == spot_id:
                current_player_ids.add(int(s.player_id))
        current_player_count = len(current_player_ids)

        connected_spot_ids: set = set()
        connected_spot_names: set = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(spot_id):
            connected_spot_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot:
                connected_spot_names.add(conn_spot.name)

        return SpotInfoDto(
            spot_id=int(spot_id),
            name=spot.name,
            description=spot.description,
            area_id=area_id,
            area_name=area_name,
            current_player_count=current_player_count,
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names,
        )

    def get_visible_context(
        self, query: GetVisibleContextQuery
    ) -> Optional[VisibleContextDto]:
        """プレイヤー視点の視界内オブジェクトを取得。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_visible_context_impl(query),
            context={"action": "get_visible_context", "player_id": query.player_id},
        )

    def _get_visible_context_impl(
        self, query: GetVisibleContextQuery
    ) -> Optional[VisibleContextDto]:
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        distance = max(0, query.distance)
        objects_in_range = physical_map.get_objects_in_range(coord, distance)

        visible_objects: List[VisibleObjectDto] = []
        for obj in objects_in_range:
            d = coord.distance_to(obj.coordinate)
            visible_objects.append(
                VisibleObjectDto(
                    object_id=obj.object_id.value,
                    object_type=obj.object_type.value,
                    x=obj.coordinate.x,
                    y=obj.coordinate.y,
                    z=obj.coordinate.z,
                    distance=d,
                    display_name=self._visible_object_display_name(obj),
                    object_kind=self._visible_object_kind(obj),
                    direction_from_player=self._direction_from_to(coord, obj.coordinate),
                    is_interactable=obj.interaction_type is not None,
                    player_id_value=int(obj.player_id) if obj.player_id is not None else None,
                    is_self=obj.player_id == player_id,
                    interaction_type=self._visible_object_interaction_type(obj),
                    available_interactions=self._visible_object_available_interactions(obj),
                )
            )

        return VisibleContextDto(
            player_id=query.player_id,
            player_name=profile.name.value,
            spot_id=int(spot_id),
            spot_name=spot.name,
            center_x=coord.x,
            center_y=coord.y,
            center_z=coord.z,
            view_distance=distance,
            visible_objects=visible_objects,
        )

    def get_available_moves(
        self, query: GetAvailableMovesQuery
    ) -> Optional[PlayerMovementOptionsDto]:
        """プレイヤーの利用可能な移動先一覧を取得（遷移条件評価込み）。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_available_moves_impl(query),
            context={"action": "get_available_moves", "player_id": query.player_id},
        )

    def _get_available_moves_impl(
        self, query: GetAvailableMovesQuery
    ) -> Optional[PlayerMovementOptionsDto]:
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(player_status.current_spot_id)
        if not spot:
            raise MapNotFoundException(int(player_status.current_spot_id))

        current_spot_id = player_status.current_spot_id
        connected_ids = self._connected_spots_provider.get_connected_spots(current_spot_id)

        available_moves: List[AvailableMoveDto] = []
        for to_spot_id in connected_ids:
            to_spot = self._spot_repository.find_by_id(to_spot_id)
            spot_name = to_spot.name if to_spot else str(to_spot_id)
            conditions_met = True
            failed_conditions: List[str] = []

            if self._transition_policy_repository and self._transition_condition_evaluator:
                conditions = self._transition_policy_repository.get_conditions(
                    current_spot_id, to_spot_id
                )
                if conditions:
                    current_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
                    weather = (
                        current_map.weather_state
                        if current_map and current_map.weather_state
                        else None
                    )
                    if weather is None:
                        from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
                        from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
                        weather = WeatherState(WeatherTypeEnum.CLEAR, 0.0)
                    context = TransitionContext(
                        player_id=query.player_id,
                        player_status=player_status,
                        from_spot_id=current_spot_id,
                        to_spot_id=to_spot_id,
                        current_weather=weather,
                    )
                    allowed, msg = self._transition_condition_evaluator.evaluate(
                        conditions, context
                    )
                    if not allowed:
                        conditions_met = False
                        failed_conditions.append(msg or "通過できません")

            available_moves.append(
                AvailableMoveDto(
                    spot_id=int(to_spot_id),
                    spot_name=spot_name,
                    road_id=0,
                    road_description="",
                    conditions_met=conditions_met,
                    failed_conditions=failed_conditions,
                )
            )

        return PlayerMovementOptionsDto(
            player_id=query.player_id,
            player_name=profile.name.value,
            current_spot_id=int(current_spot_id),
            current_spot_name=spot.name,
            available_moves=available_moves,
            total_available_moves=len(available_moves),
        )

    def get_player_current_state(
        self, query: GetPlayerCurrentStateQuery
    ) -> Optional[PlayerCurrentStateDto]:
        """プレイヤーの現在状態を一括取得（位置・スポット・天気・地形・視界・移動先・注意レベル）。未配置時は None。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_player_current_state_impl(query),
            context={"action": "get_player_current_state", "player_id": query.player_id},
        )

    def _get_player_current_state_impl(
        self, query: GetPlayerCurrentStateQuery
    ) -> Optional[PlayerCurrentStateDto]:
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)
        player_name = profile.name.value
        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        area_id = None
        area_name = None
        areas = physical_map.get_location_areas_at(coord)
        if areas:
            area_id = int(areas[0].location_id)
            area_name = areas[0].name

        current_player_ids = set()
        for s in self._player_status_repository.find_all():
            if s.current_spot_id == spot_id:
                current_player_ids.add(int(s.player_id))
        connected_spot_ids = set()
        connected_spot_names = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(spot_id):
            connected_spot_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot:
                connected_spot_names.add(conn_spot.name)

        weather_state = (
            physical_map.weather_state
            if physical_map.weather_state
            else WeatherState(WeatherTypeEnum.CLEAR, 0.0)
        )
        weather_type = weather_state.weather_type.value
        weather_intensity = weather_state.intensity

        current_terrain_type = None
        try:
            tile = physical_map.get_tile(coord)
            current_terrain_type = tile.terrain_type.type.value
        except TileNotFoundException:
            pass

        distance = max(0, query.view_distance)
        objects_in_range = physical_map.get_objects_in_range(coord, distance)
        visible_objects = []
        for obj in objects_in_range:
            d = coord.distance_to(obj.coordinate)
            visible_objects.append(
                VisibleObjectDto(
                    object_id=obj.object_id.value,
                    object_type=obj.object_type.value,
                    x=obj.coordinate.x,
                    y=obj.coordinate.y,
                    z=obj.coordinate.z,
                    distance=d,
                    display_name=self._visible_object_display_name(obj),
                    object_kind=self._visible_object_kind(obj),
                    direction_from_player=self._direction_from_to(coord, obj.coordinate),
                    is_interactable=obj.interaction_type is not None,
                    player_id_value=int(obj.player_id) if obj.player_id is not None else None,
                    is_self=obj.player_id == player_id,
                    interaction_type=self._visible_object_interaction_type(obj),
                    available_interactions=self._visible_object_available_interactions(obj),
                )
            )

        available_moves = None
        total_available_moves = None
        if query.include_available_moves:
            moves_query = GetAvailableMovesQuery(player_id=query.player_id)
            moves_result = self._get_available_moves_impl(moves_query)
            if moves_result:
                available_moves = moves_result.available_moves
                total_available_moves = moves_result.total_available_moves

        attention_level = player_status.attention_level
        is_busy = player_status.goal_spot_id is not None
        inventory_items = self._build_inventory_items(player_id)
        chest_items = self._build_chest_items(physical_map, visible_objects)
        active_conversation = self._build_active_conversation(query.player_id, visible_objects)
        usable_skills = self._build_usable_skills(query.player_id)
        attention_level_options = self._build_attention_level_options()
        can_destroy_placeable = self._can_destroy_placeable(physical_map, query.player_id)

        return PlayerCurrentStateDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(spot_id),
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
            weather_type=weather_type,
            weather_intensity=weather_intensity,
            current_terrain_type=current_terrain_type,
            visible_objects=visible_objects,
            view_distance=distance,
            available_moves=available_moves,
            total_available_moves=total_available_moves,
            attention_level=attention_level,
            is_busy=is_busy,
            inventory_items=inventory_items,
            chest_items=chest_items,
            active_conversation=active_conversation,
            usable_skills=usable_skills,
            attention_level_options=attention_level_options,
            can_destroy_placeable=can_destroy_placeable,
        )

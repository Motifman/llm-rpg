"""視界内オブジェクトの read model を構築する。"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.dtos import VisibleContextDto, VisibleObjectDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import (
        PlayerProfileRepository,
    )
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
        PhysicalMapAggregate,
    )
    from ai_rpg_world.domain.world.entity.spot import Spot


class VisibleObjectReadModelBuilder:
    """可視・実行可否・注目度を含む視界 read model を構築する。"""

    def __init__(
        self,
        player_profile_repository: "PlayerProfileRepository",
        monster_repository: Optional["MonsterRepository"] = None,
    ) -> None:
        self._player_profile_repository = player_profile_repository
        self._monster_repository = monster_repository

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
        visible_objects = self.build_visible_objects(
            physical_map=physical_map,
            origin=origin,
            distance=view_distance,
            player_id=PlayerId(player_id),
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
            if obj.coordinate != origin and not physical_map.is_visible(origin, obj.coordinate):
                continue
            visible_objects.append(
                self._build_visible_object_dto(obj=obj, origin=origin, player_id=player_id)
            )
        return visible_objects

    def build_actionable_objects(
        self, visible_objects: List[VisibleObjectDto]
    ) -> List[VisibleObjectDto]:
        return [
            obj
            for obj in visible_objects
            if obj.can_interact or obj.can_harvest or obj.can_store_in_chest or obj.can_take_from_chest
        ]

    def build_notable_objects(
        self, visible_objects: List[VisibleObjectDto]
    ) -> List[VisibleObjectDto]:
        return [obj for obj in visible_objects if obj.is_notable]

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
        is_notable, notable_reason = self._notable_state(
            obj=obj,
            player_id=player_id,
            can_interact=can_interact,
            can_harvest=can_harvest,
            can_store_in_chest=can_store_in_chest,
            can_take_from_chest=can_take_from_chest,
        )
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
            is_notable=is_notable,
            notable_reason=notable_reason,
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
        return getattr(obj, "interaction_type", None) is not None and self._is_in_action_range(origin, obj)

    def _can_harvest(self, origin: Coordinate, obj) -> bool:
        return obj.object_type == ObjectTypeEnum.RESOURCE and self._is_in_action_range(origin, obj)

    def _can_store_in_chest(self, origin: Coordinate, obj) -> bool:
        if obj.object_type != ObjectTypeEnum.CHEST or not self._is_in_action_range(origin, obj):
            return False
        interaction_data = getattr(obj, "interaction_data", {}) or {}
        return bool(interaction_data.get("is_open"))

    def _can_take_from_chest(self, origin: Coordinate, obj) -> bool:
        return self._can_store_in_chest(origin, obj)

    def _notable_state(
        self,
        *,
        obj,
        player_id: PlayerId,
        can_interact: bool,
        can_harvest: bool,
        can_store_in_chest: bool,
        can_take_from_chest: bool,
    ) -> tuple[bool, Optional[str]]:
        if obj.player_id == player_id:
            return False, None
        if can_interact or can_harvest or can_store_in_chest or can_take_from_chest:
            return True, "actionable"
        kind = self._visible_object_kind(obj)
        if kind in {"monster", "npc"}:
            return True, kind
        if kind == "player":
            return True, "player"
        return False, None

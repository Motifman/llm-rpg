"""SetDestinationService: 目的地解決と経路計算を担当するアプリケーションサービス。

リポジトリ非依存のポリシー（PassableAdjacentFinder, GlobalPathfindingService）を利用し、
目的地解決・経路計算の責務を MovementApplicationService から分離する。
"""

from dataclasses import dataclass
from typing import Optional, List, Literal

from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.passable_adjacent_finder import PassableAdjacentFinder
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAreaNotFoundException,
    ObjectNotFoundException,
    InvalidPathRequestException,
    PathNotFoundException,
)
from ai_rpg_world.application.world.contracts.commands import SetDestinationCommand
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
)


@dataclass(frozen=True)
class SetDestinationResult:
    """SetDestinationCommand の解決・経路計算結果。"""

    success: bool
    """処理が成功したか（既に到着・経路設定・経路なしのいずれかで完了）。"""

    already_at_destination: bool
    """既に到着済みで経路不要。success かつ path_found が False。"""

    path_found: bool
    """経路計算が成功したか。True のとき temp_goal, path, goal_* が有効。"""

    message: str
    """結果メッセージ（既存 DTO の message に相当）。"""

    temp_goal: Optional[Coordinate] = None
    """経路の暫定ゴール（path_found 時のみ）。"""

    path: Optional[List[Coordinate]] = None
    """計算された経路（path_found 時のみ）。"""

    goal_destination_type: Optional[Literal["spot", "location", "object"]] = None
    goal_spot_id: Optional[SpotId] = None
    goal_location_area_id: Optional[LocationAreaId] = None
    goal_world_object_id: Optional[WorldObjectId] = None


@dataclass(frozen=True)
class ReplanPathCalculationResult:
    """座標指定の経路計算結果。facade が player_status の更新に利用。"""

    success: bool
    path_planned: bool
    already_at_destination: bool
    message: str
    temp_goal: Optional[Coordinate] = None
    path: Optional[List[Coordinate]] = None
    goal_spot_id: Optional[SpotId] = None


class SetDestinationService:
    """目的地解決と経路計算を担当するアプリケーションサービス。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        physical_map_repository: PhysicalMapRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        global_pathfinding_service: GlobalPathfindingService,
    ):
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository
        self._connected_spots_provider = connected_spots_provider
        self._global_pathfinding_service = global_pathfinding_service

    def resolve_and_calculate_path(
        self, command: SetDestinationCommand
    ) -> SetDestinationResult:
        """
        SetDestinationCommand に基づき目的地を解決し、経路を計算する。
        player_status の更新は呼び出し側（facade）が担当。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        player_id = PlayerId(command.player_id)
        target_spot_id = SpotId(command.target_spot_id)

        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status:
            raise PlayerNotFoundException(command.player_id)

        current_spot_id = player_status.current_spot_id
        current_coord = player_status.current_coordinate

        if not current_spot_id or not current_coord:
            raise MovementInvalidException("Player is not placed on any map", command.player_id)

        # 目標座標の決定（destination_type に応じて）
        location_area = None
        goal_world_object_id_val: Optional[WorldObjectId] = None
        if command.destination_type == "location":
            target_physical_map = self._physical_map_repository.find_by_spot_id(
                target_spot_id
            )
            if not target_physical_map:
                raise MapNotFoundException(int(target_spot_id))
            location_area_id = LocationAreaId(command.target_location_area_id)
            try:
                location_area = target_physical_map.get_location_area(location_area_id)
            except LocationAreaNotFoundException:
                raise MovementInvalidException(
                    f"Location area {command.target_location_area_id} not found in spot {command.target_spot_id}",
                    command.player_id,
                )
            target_coord = location_area.get_reference_coordinate()
        elif command.destination_type == "object":
            physical_map_for_obj = self._physical_map_repository.find_by_spot_id(
                current_spot_id
            )
            if not physical_map_for_obj:
                raise MapNotFoundException(int(current_spot_id))
            obj_id = WorldObjectId.create(command.target_world_object_id)
            try:
                target_obj = physical_map_for_obj.get_object(obj_id)
            except ObjectNotFoundException:
                raise MovementInvalidException(
                    f"Object {command.target_world_object_id} not found in spot {int(current_spot_id)}",
                    command.player_id,
                )
            obj_coord = target_obj.coordinate
            goal_world_object_id_val = obj_id
            if current_coord.distance_to(obj_coord) <= 1:
                return SetDestinationResult(
                    success=True,
                    already_at_destination=True,
                    path_found=False,
                    message="既に目標オブジェクトの傍にいます",
                )
            target_coord = obj_coord
        else:
            target_coord = current_coord

        # 既に目的地にいる場合は経路を設定しない
        if current_spot_id == target_spot_id:
            if command.destination_type == "spot":
                return SetDestinationResult(
                    success=True,
                    already_at_destination=True,
                    path_found=False,
                    message="既に目的地のスポットにいます",
                )
            if location_area is not None and location_area.contains(current_coord):
                return SetDestinationResult(
                    success=True,
                    already_at_destination=True,
                    path_found=False,
                    message="既に目的地のロケーションにいます",
                )

        physical_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
        if not physical_map:
            raise MapNotFoundException(int(current_spot_id))

        world_object_id = WorldObjectId.create(int(player_id))
        try:
            actor = physical_map.get_actor(world_object_id)
        except ObjectNotFoundException:
            raise MovementInvalidException("Player object not found in map", command.player_id)

        capability = actor.capability or MovementCapability.normal_walk()

        if command.destination_type == "object" and goal_world_object_id_val is not None:
            target_coord = PassableAdjacentFinder.find_one(
                physical_map=physical_map,
                object_coord=target_coord,
                capability=capability,
                exclude_object_id=goal_world_object_id_val,
            )
            if target_coord is None:
                return SetDestinationResult(
                    success=False,
                    already_at_destination=False,
                    path_found=False,
                    message="目標オブジェクトの周りに通行可能な場所がありません",
                )

        try:
            temp_goal, path = self._global_pathfinding_service.calculate_global_path(
                current_spot_id=current_spot_id,
                current_coord=current_coord,
                target_spot_id=target_spot_id,
                target_coord=target_coord,
                physical_map=physical_map,
                connected_spots_provider=self._connected_spots_provider,
                world_object_id=world_object_id,
                capability=capability,
            )
        except (InvalidPathRequestException, PathNotFoundException):
            return SetDestinationResult(
                success=False,
                already_at_destination=False,
                path_found=False,
                message="目的地への経路が見つかりません",
            )

        if not path or temp_goal is None:
            return SetDestinationResult(
                success=False,
                already_at_destination=False,
                path_found=False,
                message="目的地への経路が見つかりません",
            )

        goal_location_area_id = (
            LocationAreaId(command.target_location_area_id)
            if command.destination_type == "location" and command.target_location_area_id
            else None
        )

        return SetDestinationResult(
            success=True,
            already_at_destination=False,
            path_found=True,
            message="目的地へ向かい始めました",
            temp_goal=temp_goal,
            path=path,
            goal_destination_type=command.destination_type,
            goal_spot_id=target_spot_id,
            goal_location_area_id=goal_location_area_id,
            goal_world_object_id=goal_world_object_id_val,
        )

    def calculate_path_to_coordinate(
        self,
        player_id: int,
        target_spot_id: SpotId,
        target_coordinate: Coordinate,
    ) -> ReplanPathCalculationResult:
        """
        座標指定の経路を計算する。replan 用。
        player_status の更新は呼び出し側（facade）が担当。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        player_id_vo = PlayerId(player_id)
        player_status = self._player_status_repository.find_by_id(player_id_vo)
        if not player_status:
            raise PlayerNotFoundException(player_id)

        current_spot_id = player_status.current_spot_id
        current_coord = player_status.current_coordinate
        if not current_spot_id or not current_coord:
            raise MovementInvalidException("Player is not placed on any map", player_id)

        if current_spot_id == target_spot_id and current_coord == target_coordinate:
            return ReplanPathCalculationResult(
                success=True,
                path_planned=False,
                already_at_destination=True,
                message="既に追跡先座標にいます",
            )

        physical_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
        if not physical_map:
            raise MapNotFoundException(int(current_spot_id))

        actor_id = WorldObjectId.create(player_id)
        try:
            actor = physical_map.get_actor(actor_id)
        except ObjectNotFoundException:
            raise MovementInvalidException("Player object not found in map", player_id)

        capability = actor.capability or MovementCapability.normal_walk()
        try:
            temp_goal, path = self._global_pathfinding_service.calculate_global_path(
                current_spot_id=current_spot_id,
                current_coord=current_coord,
                target_spot_id=target_spot_id,
                target_coord=target_coordinate,
                physical_map=physical_map,
                connected_spots_provider=self._connected_spots_provider,
                world_object_id=actor_id,
                capability=capability,
            )
        except (InvalidPathRequestException, PathNotFoundException):
            temp_goal, path = None, None

        if not path or temp_goal is None:
            return ReplanPathCalculationResult(
                success=False,
                path_planned=False,
                already_at_destination=False,
                message="目的地への経路が見つかりません",
            )

        return ReplanPathCalculationResult(
            success=True,
            path_planned=True,
            already_at_destination=False,
            message="追跡用の経路を更新しました",
            temp_goal=temp_goal,
            path=path,
            goal_spot_id=target_spot_id,
        )

"""ArrivalPolicy: 経路移動の到着判定を行うドメインサービス。

リポジトリに依存せず、player_status と physical_map から渡されたデータのみで判定を行う。
到着・未到着・目標消失のいずれかを返し、呼び出し側が clear_path / save の責務を持つ。
"""

from enum import Enum
from typing import Optional

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAreaNotFoundException,
    ObjectNotFoundException,
)


class ArrivalCheckResult(Enum):
    """到着判定の結果。"""

    NOT_ARRIVED = "not_arrived"
    """まだ到着していない。経路を継続する。"""

    ARRIVED = "arrived"
    """到着した。経路をクリアする。"""

    GOAL_DISAPPEARED = "goal_disappeared"
    """目標（ロケーションまたはオブジェクト）が消失した。経路をクリアする。"""


class ArrivalPolicy:
    """
    経路移動の到着判定を行うドメインサービス。
    リポジトリ非依存。
    """

    @classmethod
    def check(
        cls,
        player_status: PlayerStatusAggregate,
        physical_map: Optional[PhysicalMapAggregate],
    ) -> ArrivalCheckResult:
        """
        現在地が目的地（spot / location / object）に到着したか判定する。

        Args:
            player_status: プレイヤーステータス集約（goal_* と current_* を持つ）
            physical_map: 現在スポットの物理マップ。location または object 型のとき必要。
                          spot 型のみのときは None でよい。

        Returns:
            ArrivalCheckResult: NOT_ARRIVED / ARRIVED / GOAL_DISAPPEARED
        """
        goal_spot_id = player_status.goal_spot_id
        current_spot_id = player_status.current_spot_id
        current_coord = player_status.current_coordinate

        if not goal_spot_id or current_spot_id != goal_spot_id:
            return ArrivalCheckResult.NOT_ARRIVED

        goal_type = player_status.goal_destination_type

        if goal_type == "spot":
            return ArrivalCheckResult.ARRIVED

        if goal_type == "location":
            goal_location_area_id = player_status.goal_location_area_id
            if not goal_location_area_id or not physical_map or not current_coord:
                return ArrivalCheckResult.NOT_ARRIVED
            try:
                loc_area = physical_map.get_location_area(goal_location_area_id)
                if loc_area.contains(current_coord):
                    return ArrivalCheckResult.ARRIVED
                return ArrivalCheckResult.NOT_ARRIVED
            except LocationAreaNotFoundException:
                return ArrivalCheckResult.GOAL_DISAPPEARED

        if goal_type == "object":
            goal_world_object_id = player_status.goal_world_object_id
            if not goal_world_object_id or not physical_map or not current_coord:
                return ArrivalCheckResult.NOT_ARRIVED
            try:
                target_obj = physical_map.get_object(goal_world_object_id)
                if current_coord.distance_to(target_obj.coordinate) <= 1:
                    return ArrivalCheckResult.ARRIVED
                return ArrivalCheckResult.NOT_ARRIVED
            except ObjectNotFoundException:
                return ArrivalCheckResult.GOAL_DISAPPEARED

        return ArrivalCheckResult.NOT_ARRIVED

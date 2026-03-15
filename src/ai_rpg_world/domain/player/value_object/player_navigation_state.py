"""
PlayerNavigationState: プレイヤーの位置・経路・目的地を表す不変の値オブジェクト。

PlayerStatusAggregate が持つ移動関連の状態をカプセル化する。
planned_path は [current, next1, next2, ...] の形式。advance_step で経路を1ステップ進める。
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple, Literal, Sequence

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


GoalDestinationType = Literal["spot", "location", "object"]


@dataclass(frozen=True)
class PlayerNavigationState:
    """
    プレイヤーの移動・経路・目的地を表す値オブジェクト。
    不変。変更時は新しいインスタンスを返す。
    """

    current_spot_id: Optional[SpotId]
    current_coordinate: Optional[Coordinate]
    current_destination: Optional[Coordinate]
    planned_path: Tuple[Coordinate, ...]
    goal_destination_type: Optional[GoalDestinationType]
    goal_spot_id: Optional[SpotId]
    goal_location_area_id: Optional[LocationAreaId]
    goal_world_object_id: Optional[WorldObjectId]

    @classmethod
    def empty(cls) -> "PlayerNavigationState":
        """初期状態を作成する。"""
        return cls(
            current_spot_id=None,
            current_coordinate=None,
            current_destination=None,
            planned_path=(),
            goal_destination_type=None,
            goal_spot_id=None,
            goal_location_area_id=None,
            goal_world_object_id=None,
        )

    @classmethod
    def from_parts(
        cls,
        current_spot_id: Optional[SpotId] = None,
        current_coordinate: Optional[Coordinate] = None,
        current_destination: Optional[Coordinate] = None,
        planned_path: Optional[Sequence[Coordinate]] = None,
        goal_destination_type: Optional[GoalDestinationType] = None,
        goal_spot_id: Optional[SpotId] = None,
        goal_location_area_id: Optional[LocationAreaId] = None,
        goal_world_object_id: Optional[WorldObjectId] = None,
    ) -> "PlayerNavigationState":
        """個別フィールドから値を組み立てて構築する（永続化層・テスト用）。"""
        path = planned_path if planned_path is not None else []
        path_tuple = tuple(path) if isinstance(path, (list, tuple)) else tuple(path)
        return cls(
            current_spot_id=current_spot_id,
            current_coordinate=current_coordinate,
            current_destination=current_destination,
            planned_path=path_tuple,
            goal_destination_type=goal_destination_type,
            goal_spot_id=goal_spot_id,
            goal_location_area_id=goal_location_area_id,
            goal_world_object_id=goal_world_object_id,
        )

    def with_destination_set(
        self,
        destination: Coordinate,
        path: Sequence[Coordinate],
        goal_destination_type: Optional[GoalDestinationType] = None,
        goal_spot_id: Optional[SpotId] = None,
        goal_location_area_id: Optional[LocationAreaId] = None,
        goal_world_object_id: Optional[WorldObjectId] = None,
    ) -> "PlayerNavigationState":
        """目的地と経路、および到着判定用の目標情報を設定した新しい状態を返す。"""
        path_tuple = tuple(path) if path else ()
        return PlayerNavigationState(
            current_spot_id=self.current_spot_id,
            current_coordinate=self.current_coordinate,
            current_destination=destination,
            planned_path=path_tuple,
            goal_destination_type=goal_destination_type,
            goal_spot_id=goal_spot_id,
            goal_location_area_id=goal_location_area_id,
            goal_world_object_id=goal_world_object_id,
        )

    def cleared(self) -> "PlayerNavigationState":
        """経路と目標情報をクリアした新しい状態を返す。"""
        return PlayerNavigationState(
            current_spot_id=self.current_spot_id,
            current_coordinate=self.current_coordinate,
            current_destination=None,
            planned_path=(),
            goal_destination_type=None,
            goal_spot_id=None,
            goal_location_area_id=None,
            goal_world_object_id=None,
        )

    def advance_step(self) -> Tuple[Optional[Coordinate], "PlayerNavigationState"]:
        """
        経路を1ステップ進める。
        planned_path[0] は現在地、[1] は次に進むべき座標。

        Returns:
            (次に進むべき座標, 新しい状態)。経路が空または1要素以下の場合は (None, cleared状態)。
        """
        if len(self.planned_path) < 2:
            return (None, self.cleared())

        next_coord = self.planned_path[1]
        remaining = (self.planned_path[0],) + self.planned_path[2:]

        if len(remaining) <= 1:
            new_state = self.cleared()
        else:
            new_state = PlayerNavigationState(
                current_spot_id=self.current_spot_id,
                current_coordinate=self.current_coordinate,
                current_destination=self.current_destination,
                planned_path=remaining,
                goal_destination_type=self.goal_destination_type,
                goal_spot_id=self.goal_spot_id,
                goal_location_area_id=self.goal_location_area_id,
                goal_world_object_id=self.goal_world_object_id,
            )

        return (next_coord, new_state)

    def with_location_updated(
        self,
        spot_id: SpotId,
        coordinate: Coordinate,
    ) -> "PlayerNavigationState":
        """現在地を更新した新しい状態を返す。"""
        return PlayerNavigationState(
            current_spot_id=spot_id,
            current_coordinate=coordinate,
            current_destination=self.current_destination,
            planned_path=self.planned_path,
            goal_destination_type=self.goal_destination_type,
            goal_spot_id=self.goal_spot_id,
            goal_location_area_id=self.goal_location_area_id,
            goal_world_object_id=self.goal_world_object_id,
        )

    def planned_path_as_list(self) -> List[Coordinate]:
        """計画された経路を List で返す（aggregate の planned_path プロパティ互換）。"""
        return list(self.planned_path)

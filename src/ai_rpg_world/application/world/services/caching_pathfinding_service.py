"""
経路キャッシュ付き PathfindingService のデコレータ。
同じゴールへの経路を数ティック使い回し、経路探索の負荷を軽減する。
キャッシュは「現在位置がキャッシュ経路上にあるとき」サフィックスを返す形で再利用する。
"""

from typing import List, Optional, Tuple, TYPE_CHECKING, Dict, Any

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.pathfinding_strategy import PathfindingMap
from ai_rpg_world.domain.world.exception.map_exception import (
    PathNotFoundException,
    InvalidPathRequestException,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId
    from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider


def _cache_key(
    spot_id: "SpotId",
    goal: Coordinate,
    capability: MovementCapability,
    allow_partial_path: bool,
    smooth_path: bool,
) -> Tuple[Any, ...]:
    """キャッシュキーを組み立てる。全て hashable であること。"""
    return (spot_id, goal, capability, allow_partial_path, smooth_path)


class CachingPathfindingService:
    """
    PathfindingService をラップし、同じ (spot_id, goal, capability) に対する
    経路を再利用するデコレータ。現在位置がキャッシュ経路上にある場合は
    そのサフィックスを返し、A* の再計算を避ける。
    """

    def __init__(
        self,
        delegate: PathfindingService,
        time_provider: Optional["GameTimeProvider"] = None,
        ttl_ticks: Optional[int] = None,
    ):
        """
        Args:
            delegate: 実際の経路探索を行う PathfindingService
            time_provider: TTL に使う現在ティック取得用。None の場合は TTL なし
            ttl_ticks: キャッシュ有効ティック数。time_provider が None の場合は無視
        """
        self._delegate = delegate
        self._time_provider = time_provider
        self._ttl_ticks = ttl_ticks if time_provider is not None else None
        # (path, stored_tick_value). stored_tick_value は TTL なしのとき 0
        self._cache: Dict[Tuple[Any, ...], Tuple[List[Coordinate], int]] = {}

    def calculate_path(
        self,
        start: Coordinate,
        goal: Coordinate,
        map_data: PathfindingMap,
        capability: MovementCapability,
        ignore_errors: bool = False,
        max_iterations: int = 1000,
        allow_partial_path: bool = False,
        smooth_path: bool = True,
        exclude_object_id: Optional["WorldObjectId"] = None,
    ) -> List[Coordinate]:
        """
        開始地点から目標地点までの経路を算出する。
        spot_id が map_data から取得できる場合のみキャッシュを利用する。
        例外は delegate と同様（InvalidPathRequestException, PathNotFoundException）。
        """
        spot_id = getattr(map_data, "spot_id", None)
        if spot_id is None:
            return self._delegate.calculate_path(
                start=start,
                goal=goal,
                map_data=map_data,
                capability=capability,
                ignore_errors=ignore_errors,
                max_iterations=max_iterations,
                allow_partial_path=allow_partial_path,
                smooth_path=smooth_path,
                exclude_object_id=exclude_object_id,
            )

        key = _cache_key(spot_id, goal, capability, allow_partial_path, smooth_path)
        current_tick = 0
        if self._time_provider is not None:
            current_tick = self._time_provider.get_current_tick().value

        # キャッシュヒット: 同じキーで経路があり、start が経路上にある場合
        if key in self._cache:
            cached_path, stored_tick = self._cache[key]
            if self._ttl_ticks is not None and current_tick > stored_tick + self._ttl_ticks:
                del self._cache[key]
            else:
                for i, coord in enumerate(cached_path):
                    if coord == start:
                        suffix = cached_path[i:]
                        return list(suffix)
                # start が経路上にない場合はキャッシュミス（経路は残して delegate で再計算）

        # デリゲート呼び出し
        path = self._delegate.calculate_path(
            start=start,
            goal=goal,
            map_data=map_data,
            capability=capability,
            ignore_errors=ignore_errors,
            max_iterations=max_iterations,
            allow_partial_path=allow_partial_path,
            smooth_path=smooth_path,
            exclude_object_id=exclude_object_id,
        )

        # 経路が得られた場合のみキャッシュに格納（空リストは格納しない）
        if path:
            self._cache[key] = (list(path), current_tick)

        return path

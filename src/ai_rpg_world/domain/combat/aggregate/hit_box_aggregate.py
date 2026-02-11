from typing import List, Set
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
)
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxInactiveException
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick


class HitBoxAggregate(AggregateRoot):
    """
    当たり判定（HitBox）を管理する集約。
    物理マップ上に配置され、一定期間存在するか、移動しながら衝突判定を行う。
    """

    def __init__(
        self,
        hit_box_id: HitBoxId,
        owner_id: WorldObjectId,
        shape: HitBoxShape,
        initial_coordinate: Coordinate,
        start_tick: WorldTick,
        duration: int,
        power_multiplier: float = 1.0
    ):
        super().__init__()
        self._hit_box_id = hit_box_id
        self._owner_id = owner_id
        self._shape = shape
        self._current_coordinate = initial_coordinate
        self._previous_coordinate = initial_coordinate
        self._start_tick = start_tick
        self._duration = duration
        self._power_multiplier = power_multiplier
        self._is_active = True
        self._hit_targets: Set[WorldObjectId] = set()

    @classmethod
    def create(
        cls,
        hit_box_id: HitBoxId,
        owner_id: WorldObjectId,
        shape: HitBoxShape,
        initial_coordinate: Coordinate,
        start_tick: WorldTick,
        duration: int,
        power_multiplier: float = 1.0,
    ) -> "HitBoxAggregate":
        """HitBoxを新規作成する。"""
        from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException
        if duration <= 0:
            raise HitBoxValidationException(f"duration must be greater than 0. duration: {duration}")
        if power_multiplier <= 0:
            raise HitBoxValidationException(f"power_multiplier must be greater than 0. power_multiplier: {power_multiplier}")

        hit_box = cls(
            hit_box_id=hit_box_id,
            owner_id=owner_id,
            shape=shape,
            initial_coordinate=initial_coordinate,
            start_tick=start_tick,
            duration=duration,
            power_multiplier=power_multiplier,
        )
        hit_box.add_event(HitBoxCreatedEvent.create(
            aggregate_id=hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=owner_id,
            initial_coordinate=initial_coordinate,
            duration=duration,
            power_multiplier=power_multiplier,
            shape_cell_count=len(shape.relative_coordinates),
        ))
        return hit_box

    @property
    def hit_box_id(self) -> HitBoxId:
        return self._hit_box_id

    @property
    def owner_id(self) -> WorldObjectId:
        return self._owner_id

    @property
    def current_coordinate(self) -> Coordinate:
        return self._current_coordinate

    @property
    def power_multiplier(self) -> float:
        return self._power_multiplier

    @property
    def is_active(self) -> bool:
        return self._is_active

    def move_to(self, new_coordinate: Coordinate):
        """位置を更新し、移動前の位置を保持する（経路判定のため）"""
        if not self._is_active:
            raise HitBoxInactiveException(f"HitBox {self._hit_box_id} is inactive")

        if self._current_coordinate == new_coordinate:
            return

        old_coordinate = self._current_coordinate
        self._previous_coordinate = self._current_coordinate
        self._current_coordinate = new_coordinate
        self.add_event(HitBoxMovedEvent.create(
            aggregate_id=self._hit_box_id,
            aggregate_type="HitBoxAggregate",
            from_coordinate=old_coordinate,
            to_coordinate=new_coordinate,
        ))

    def is_expired(self, current_tick: WorldTick) -> bool:
        """持続時間が終了しているか判定する"""
        return current_tick.value >= (self._start_tick.value + self._duration)

    def deactivate(self, reason: str = "manual"):
        """HitBoxを無効化する（寿命終了や衝突消滅時）"""
        if not self._is_active:
            return

        self._is_active = False
        self.add_event(HitBoxDeactivatedEvent.create(
            aggregate_id=self._hit_box_id,
            aggregate_type="HitBoxAggregate",
            reason=reason,
        ))

    def has_hit(self, target_id: WorldObjectId) -> bool:
        """指定したターゲットに既にヒット済みか確認する"""
        return target_id in self._hit_targets

    def record_hit(self, target_id: WorldObjectId):
        """ヒットしたターゲットを記録する（多段ヒット防止用）"""
        if not self._is_active:
            raise HitBoxInactiveException(f"HitBox {self._hit_box_id} is inactive")
        if target_id == self._owner_id:
            return
        if target_id in self._hit_targets:
            return

        self._hit_targets.add(target_id)
        self.add_event(HitBoxHitRecordedEvent.create(
            aggregate_id=self._hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=self._owner_id,
            target_id=target_id,
            hit_coordinate=self._current_coordinate,
        ))

    def get_all_covered_coordinates(self) -> List[Coordinate]:
        """
        現在の位置、および前回の位置からの移動経路上に含まれる全ての絶対座標を返す。
        リアルタイムの当たり判定精度を向上させるためのロジック。
        """
        # 単純な移動（テレポート）ではなく、1ティック間の移動経路を補間する
        # ここでは簡易的なグリッド補間（直線上の座標を全て取得）を実装
        path = self._calculate_path(self._previous_coordinate, self._current_coordinate)
        
        covered: Set[Coordinate] = set()
        for pos in path:
            covered.update(self._shape.to_absolute(pos))
        
        return list(covered)

    def _calculate_path(self, start: Coordinate, end: Coordinate) -> List[Coordinate]:
        """
        2点間のグリッド上の直線座標リストを計算する。
        Amanatides-Wooのアルゴリズムに基づいた 3D DDA (Supercover) を採用し、
        線が通過するすべてのグリッドセルを網羅する。
        """
        if start == end:
            return [start]

        coords = []
        x, y, z = start.x, start.y, start.z
        x_end, y_end, z_end = end.x, end.y, end.z

        dx = x_end - x
        dy = y_end - y
        dz = z_end - z

        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        step_z = 1 if dz > 0 else -1 if dz < 0 else 0

        # 各軸の境界を跨ぐまでの「時間」を計算
        # 整数グリッドなので、初期の境界までの距離を dx で割る
        def get_t_max(start_val, delta_val, step):
            if step == 0:
                return float('inf')
            # 次の境界値（整数値）
            next_boundary = start_val + (1 if step > 0 else 0) if step != 0 else start_val
            # 浮動小数点計算を避けるため、deltaの絶対値を使用
            # ただしここでは正確な交差判定のため float を使用
            return abs((next_boundary - (start_val + 0.5)) / delta_val) if delta_val != 0 else float('inf')

        # グリッドの中心(x+0.5)からスタートすると考える
        t_max_x = abs((step_x * 0.5) / dx) if dx != 0 else float('inf')
        t_max_y = abs((step_y * 0.5) / dy) if dy != 0 else float('inf')
        t_max_z = abs((step_z * 0.5) / dz) if dz != 0 else float('inf')

        t_delta_x = abs(1.0 / dx) if dx != 0 else float('inf')
        t_delta_y = abs(1.0 / dy) if dy != 0 else float('inf')
        t_delta_z = abs(1.0 / dz) if dz != 0 else float('inf')

        # 始点を追加
        coords.append(Coordinate(x, y, z))

        while True:
            if x == x_end and y == y_end and z == z_end:
                break
            
            if t_max_x < t_max_y:
                if t_max_x < t_max_z:
                    x += step_x
                    t_max_x += t_delta_x
                else:
                    z += step_z
                    t_max_z += t_delta_z
            else:
                if t_max_y < t_max_z:
                    y += step_y
                    t_max_y += t_delta_y
                else:
                    z += step_z
                    t_max_z += t_delta_z
            
            coords.append(Coordinate(x, y, z))

        return coords

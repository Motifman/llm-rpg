from typing import List, Set, Tuple, Any
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxInactiveException
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import (
    ObstacleCollisionPolicy,
    TargetCollisionPolicy,
)
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.common.value_object import WorldTick


class HitBoxAggregate(AggregateRoot):
    """
    当たり判定（HitBox）を管理する集約。
    物理マップ上に配置され、一定期間存在するか、移動しながら衝突判定を行う。
    """

    def __init__(
        self,
        hit_box_id: HitBoxId,
        spot_id: SpotId,
        owner_id: WorldObjectId,
        shape: HitBoxShape,
        initial_coordinate: Coordinate,
        start_tick: WorldTick,
        duration: int,
        power_multiplier: float = 1.0,
        velocity: HitBoxVelocity = HitBoxVelocity.zero(),
        attacker_stats: BaseStats | None = None,
        target_collision_policy: TargetCollisionPolicy = TargetCollisionPolicy.KEEP_ACTIVE,
        obstacle_collision_policy: ObstacleCollisionPolicy = ObstacleCollisionPolicy.PASS_THROUGH,
        hit_effects: Tuple[HitEffect, ...] = (),
        movement_capability: MovementCapability = MovementCapability.normal_walk(),
        activation_tick: int | None = None,
        skill_id: str | None = None,
    ):
        super().__init__()
        self._hit_box_id = hit_box_id
        self._spot_id = spot_id
        self._owner_id = owner_id
        self._shape = shape
        self._current_coordinate = initial_coordinate
        self._previous_coordinate = initial_coordinate
        self._precise_x = float(initial_coordinate.x)
        self._precise_y = float(initial_coordinate.y)
        self._precise_z = float(initial_coordinate.z)
        self._start_tick = start_tick
        self._duration = duration
        self._power_multiplier = power_multiplier
        self._velocity = velocity
        self._attacker_stats = attacker_stats
        self._target_collision_policy = target_collision_policy
        self._obstacle_collision_policy = obstacle_collision_policy
        self._hit_effects = hit_effects
        self._movement_capability = movement_capability
        self._activation_tick = activation_tick or start_tick.value
        self._skill_id = skill_id
        self._is_active = True
        self._hit_targets: Set[WorldObjectId] = set()
        self._hit_obstacle_coordinates: Set[Coordinate] = set()

    @classmethod
    def create(
        cls,
        hit_box_id: HitBoxId,
        spot_id: SpotId,
        owner_id: WorldObjectId,
        shape: HitBoxShape,
        initial_coordinate: Coordinate,
        start_tick: WorldTick,
        duration: int,
        power_multiplier: float = 1.0,
        velocity: HitBoxVelocity = HitBoxVelocity.zero(),
        attacker_stats: BaseStats | None = None,
        target_collision_policy: TargetCollisionPolicy = TargetCollisionPolicy.KEEP_ACTIVE,
        obstacle_collision_policy: ObstacleCollisionPolicy = ObstacleCollisionPolicy.PASS_THROUGH,
        hit_effects: List[HitEffect] | None = None,
        movement_capability: MovementCapability | None = None,
        activation_tick: int | None = None,
        skill_id: str | None = None,
    ) -> "HitBoxAggregate":
        """HitBoxを新規作成する。"""
        from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException
        if duration <= 0:
            raise HitBoxValidationException(f"duration must be greater than 0. duration: {duration}")
        if power_multiplier <= 0:
            raise HitBoxValidationException(f"power_multiplier must be greater than 0. power_multiplier: {power_multiplier}")
        
        start_val = start_tick.value
        act_val = activation_tick if activation_tick is not None else start_val
        if act_val < start_val:
            raise HitBoxValidationException(f"activation_tick ({act_val}) cannot be earlier than start_tick ({start_val})")

        effects = tuple(hit_effects or [])
        capability = movement_capability or MovementCapability.normal_walk()

        hit_box = cls(
            hit_box_id=hit_box_id,
            spot_id=spot_id,
            owner_id=owner_id,
            shape=shape,
            initial_coordinate=initial_coordinate,
            start_tick=start_tick,
            duration=duration,
            power_multiplier=power_multiplier,
            velocity=velocity,
            attacker_stats=attacker_stats,
            target_collision_policy=target_collision_policy,
            obstacle_collision_policy=obstacle_collision_policy,
            hit_effects=effects,
            movement_capability=capability,
            activation_tick=activation_tick,
            skill_id=skill_id,
        )
        hit_box.add_event(HitBoxCreatedEvent.create(
            aggregate_id=hit_box_id,
            aggregate_type="HitBoxAggregate",
            spot_id=spot_id,
            owner_id=owner_id,
            initial_coordinate=initial_coordinate,
            duration=duration,
            power_multiplier=power_multiplier,
            shape_cell_count=len(shape.relative_coordinates),
            effect_count=len(effects),
            activation_tick=hit_box.activation_tick,
            skill_id=skill_id,
        ))
        return hit_box

    @property
    def hit_box_id(self) -> HitBoxId:
        return self._hit_box_id

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

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
    def attacker_stats(self) -> BaseStats | None:
        return self._attacker_stats

    @property
    def velocity(self) -> HitBoxVelocity:
        return self._velocity

    @property
    def hit_effects(self) -> Tuple[HitEffect, ...]:
        return self._hit_effects

    @property
    def movement_capability(self) -> MovementCapability:
        return self._movement_capability

    @property
    def activation_tick(self) -> int:
        return self._activation_tick

    @property
    def skill_id(self) -> str | None:
        return self._skill_id

    def is_activated(self, current_tick: WorldTick) -> bool:
        """有効化時刻に達しているか判定する"""
        return current_tick.value >= self._activation_tick

    @property
    def precise_position(self) -> Tuple[float, float, float]:
        """内部的な連続位置（衝突判定前の計算用）を返す。"""
        return (self._precise_x, self._precise_y, self._precise_z)

    @property
    def is_active(self) -> bool:
        return self._is_active

    def should_deactivate_on_target_hit(self) -> bool:
        return self._target_collision_policy == TargetCollisionPolicy.DEACTIVATE

    def can_pass_through_obstacles(self) -> bool:
        return self._obstacle_collision_policy == ObstacleCollisionPolicy.PASS_THROUGH

    def on_tick(self, current_tick: WorldTick, step_ratio: float = 1.0) -> None:
        """
        ティック進行時の更新。
        有効化時刻のチェック、寿命切れ判定後、速度が設定されていれば移動を実行する。
        """
        if not self._is_active:
            return

        # 前回の位置を現在の位置で更新（有効化前でも経路計算の起点は必要）
        self._previous_coordinate = self._current_coordinate

        # 有効化時刻に達していない場合は何もしない
        if current_tick.value < self._activation_tick:
            return

        if self.is_expired(current_tick):
            self.deactivate(reason="expired")
            return

        # 前回の位置を現在の位置で更新し、このサブステップの移動経路を計算できるようにする
        self._previous_coordinate = self._current_coordinate

        if self._velocity.is_stationary:
            return

        next_x, next_y, next_z = self._velocity.apply_to_precise(
            self._precise_x,
            self._precise_y,
            self._precise_z,
            step_ratio=step_ratio,
        )

        projected = Coordinate(
            int(next_x),
            int(next_y),
            int(next_z),
        )

        self._precise_x, self._precise_y, self._precise_z = next_x, next_y, next_z
        self._move_to_step(projected)

    def teleport_to(self, new_coordinate: Coordinate):
        """指定した座標にテレポートする。小数精度の位置も同期される。"""
        self._update_location(new_coordinate, sync_precise=True)

    def _move_to_step(self, new_coordinate: Coordinate):
        """サブステップ移動用の内部メソッド。小数精度の位置は更新済みであることを前提とする。"""
        self._update_location(new_coordinate, sync_precise=False)

    def _update_location(self, new_coordinate: Coordinate, sync_precise: bool):
        """位置を更新し、移動前の位置を保持する（経路判定のため）"""
        if not self._is_active:
            raise HitBoxInactiveException(f"HitBox {self._hit_box_id} is inactive")

        if self._current_coordinate == new_coordinate:
            return

        old_coordinate = self._current_coordinate
        self._previous_coordinate = self._current_coordinate
        self._current_coordinate = new_coordinate
        if sync_precise:
            self._precise_x = float(new_coordinate.x)
            self._precise_y = float(new_coordinate.y)
            self._precise_z = float(new_coordinate.z)
        self.add_event(HitBoxMovedEvent.create(
            aggregate_id=self._hit_box_id,
            aggregate_type="HitBoxAggregate",
            from_coordinate=old_coordinate,
            to_coordinate=new_coordinate,
        ))

    def move_to(self, new_coordinate: Coordinate, sync_precise: bool = True):
        """
        【非推奨】teleport_to または内部の移動処理を使用してください。
        後方互換性とテストのために残していますが、将来的に削除される可能性があります。
        """
        self._update_location(new_coordinate, sync_precise=sync_precise)

    def is_expired(self, current_tick: WorldTick) -> bool:
        """持続時間が終了しているか判定する"""
        # 寿命は有効化されてからの経過時間で判定すべき
        return current_tick.value >= (self._activation_tick + self._duration)

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

        if self.should_deactivate_on_target_hit():
            self.deactivate(reason="target_collision")

    def record_obstacle_collision(self, collision_coordinate: Coordinate) -> None:
        """障害物との衝突を記録し、ポリシーに応じて消滅させる。"""
        if not self._is_active:
            raise HitBoxInactiveException(f"HitBox {self._hit_box_id} is inactive")

        if collision_coordinate in self._hit_obstacle_coordinates:
            return

        self._hit_obstacle_coordinates.add(collision_coordinate)
        self.add_event(HitBoxObstacleCollidedEvent.create(
            aggregate_id=self._hit_box_id,
            aggregate_type="HitBoxAggregate",
            collision_coordinate=collision_coordinate,
            obstacle_collision_policy=self._obstacle_collision_policy.value,
        ))

        if not self.can_pass_through_obstacles():
            self.deactivate(reason="obstacle_collision")

    def get_aggregated_events(self) -> List[DomainEvent]:
        """
        蓄積されたイベントを重複抑制して返す。
        同一ティック内での冗長な移動や衝突イベントを集約する。
        """
        events = self.get_events()
        aggregated: List[DomainEvent] = []
        seen_keys = set()

        for event in events:
            key: Any = None
            if isinstance(event, HitBoxMovedEvent):
                key = ("moved", event.from_coordinate, event.to_coordinate)
            elif isinstance(event, HitBoxObstacleCollidedEvent):
                key = ("obstacle", event.collision_coordinate, event.obstacle_collision_policy)
            elif isinstance(event, HitBoxHitRecordedEvent):
                key = ("target_hit", event.target_id, event.hit_coordinate)

            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)

            aggregated.append(event)

        return aggregated

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

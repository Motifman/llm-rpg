import math
import random
from typing import Optional, List, Tuple
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum, ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.hostility_service import HostilityService, ConfigurableHostilityService
from ai_rpg_world.domain.world.exception.map_exception import NotAnActorException, PathNotFoundException, InvalidPathRequestException
from ai_rpg_world.domain.world.event.behavior_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
    BehaviorStuckEvent
)


class BehaviorService:
    """アクターの自律的な行動を制御するドメインサービス"""

    def __init__(self, pathfinding_service: PathfindingService, hostility_service: HostilityService = None):
        self._pathfinding_service = pathfinding_service
        self._hostility_service = hostility_service or ConfigurableHostilityService()

    def plan_next_move(
        self,
        actor_id: WorldObjectId,
        map_aggregate: PhysicalMapAggregate
    ) -> Optional[Coordinate]:
        """
        アクターの現在の状態に基づいて次の移動先を決定する。
        
        Returns:
            次に移動すべき座標。移動の必要がない場合はNone。
        """
        actor = map_aggregate.get_object(actor_id)
        component = actor.component
        
        if not isinstance(component, AutonomousBehaviorComponent):
            return None

        # 初期位置の保持
        if component.initial_position is None:
            component.initial_position = actor.coordinate

        old_state = component.state
        
        # 1. 視界内のターゲットをチェック
        target = self._find_visible_target(actor, map_aggregate, component)
        
        if target:
            # ターゲットを発見した場合
            component.spot_target(target.object_id, target.coordinate)
            if old_state != component.state:
                self._publish_state_changed(map_aggregate, actor_id, old_state, component.state)
                map_aggregate.add_event(TargetSpottedEvent.create(
                    aggregate_id=actor_id,
                    aggregate_type="Actor",
                    actor_id=actor_id,
                    target_id=target.object_id,
                    coordinate=target.coordinate
                ))
        else:
            # ターゲットが見えない場合
            if component.target_id:
                # 追跡中または逃走中だったが見失った
                lost_target_id = component.target_id
                last_coord = component.last_known_target_position
                component.lose_target()
                if old_state != component.state:
                    self._publish_state_changed(map_aggregate, actor_id, old_state, component.state)
                    if last_coord:
                        map_aggregate.add_event(TargetLostEvent.create(
                            aggregate_id=actor_id,
                            aggregate_type="Actor",
                            actor_id=actor_id,
                            target_id=lost_target_id,
                            last_known_coordinate=last_coord
                        ))

        # 2. 状態に応じた移動先計算
        if component.state == BehaviorStateEnum.FLEE:
            return self._calculate_flee_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.CHASE:
            return self._calculate_chase_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.SEARCH:
            return self._calculate_search_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.PATROL:
            return self._calculate_patrol_move(actor, component, map_aggregate)
        elif component.state == BehaviorStateEnum.RETURN:
            return self._calculate_return_move(actor, component, map_aggregate)
        
        return None

    def _publish_state_changed(self, map_aggregate, actor_id, old_state, new_state):
        map_aggregate.add_event(ActorStateChangedEvent.create(
            aggregate_id=actor_id,
            aggregate_type="Actor",
            actor_id=actor_id,
            old_state=old_state,
            new_state=new_state
        ))

    def _find_visible_target(
        self, 
        actor, 
        map_aggregate: PhysicalMapAggregate, 
        component: AutonomousBehaviorComponent
    ):
        """視界内に敵対的なオブジェクトがいるか確認し、最も近いものを返す (FOVを考慮)"""
        # 近傍のオブジェクトを取得（効率のため視界範囲内のみ）
        nearby_objects = map_aggregate.get_objects_in_range(actor.coordinate, component.vision_range)
        
        visible_hostiles = []
        for obj in nearby_objects:
            # 自分自身は除外
            if obj.object_id == actor.object_id:
                continue
                
            # アクター（プレイヤー含む）のみを対象とする
            if not obj.is_actor:
                continue

            # 敵対関係チェック
            if not self._hostility_service.is_hostile(component, obj.component):
                continue

            # 1. 物理的な視線チェック
            if not map_aggregate.is_visible(actor.coordinate, obj.coordinate):
                continue
            
            # 2. 視野角 (FOV) チェック
            if self._is_within_fov(actor, obj.coordinate, component):
                visible_hostiles.append(obj)
        
        if not visible_hostiles:
            return None
            
        # 最も近い敵対オブジェクトを選択
        return min(visible_hostiles, key=lambda p: actor.coordinate.euclidean_distance_to(p.coordinate))

    def _is_within_fov(
        self, 
        actor, 
        target_coord: Coordinate, 
        component: AutonomousBehaviorComponent
    ) -> bool:
        """ターゲットがアクターの視野角 (FOV) 内にいるか判定する"""
        if component.fov_angle >= 360.0:
            return True
            
        # 自身と同じ座標なら視界内とみなす
        if actor.coordinate == target_coord:
            return True

        # アクターの前方ベクトルを取得 (XY平面)
        dir_vectors = {
            DirectionEnum.NORTH: (0, -1),
            DirectionEnum.SOUTH: (0, 1),
            DirectionEnum.EAST: (1, 0),
            DirectionEnum.WEST: (-1, 0),
        }
        
        actor_dir = dir_vectors.get(component.direction)
        if actor_dir is None:
            # UP/DOWN などの垂直方向を向いている場合は、水平方向は全方位カバーするとみなす
            return True

        # ターゲットへのベクトル (XY平面)
        target_vec = (target_coord.x - actor.coordinate.x, target_coord.y - actor.coordinate.y)
        
        # ターゲットが同一XY座標でZが異なる場合
        if target_vec == (0, 0):
            return True

        # ターゲットへの角度を計算
        angle_to_target = math.degrees(math.atan2(target_vec[1], target_vec[0]))
        # アクターの向きの角度を計算
        angle_actor = math.degrees(math.atan2(actor_dir[1], actor_dir[0]))
        
        # 角度差を計算 (-180 to 180)
        diff = (angle_to_target - angle_actor + 180) % 360 - 180
        
        # 角度差の絶対値が FOVの半分以内なら視界内
        return abs(diff) <= (component.fov_angle / 2.0)

    def _calculate_chase_move(self, actor, component, map_aggregate) -> Optional[Coordinate]:
        """追跡時の次の移動先を計算"""
        if not component.last_known_target_position:
            return None
        
        return self._get_next_step_to(actor, component.last_known_target_position, map_aggregate, component)

    def _calculate_flee_move(self, actor, component, map_aggregate) -> Optional[Coordinate]:
        """逃走時の次の移動先を計算（ターゲットから離れる方向へパスを引く）"""
        target_id = component.target_id
        if not target_id:
            return self._calculate_return_move(actor, component, map_aggregate)
            
        try:
            target = map_aggregate.get_object(target_id)
        except Exception:
            component.lose_target()
            return self._calculate_return_move(actor, component, map_aggregate)

        # ターゲットから離れるための「ゴール地点」を探す
        flee_goal = self._find_flee_goal(actor, target.coordinate, component, map_aggregate)
        if not flee_goal:
            # 逃げ場がない場合はその場に留まるか、攻撃的な挙動に切り替えることも考えられるが
            # ここでは単に None を返す
            return None

        return self._get_next_step_to(actor, flee_goal, map_aggregate, component)

    def _find_flee_goal(
        self, 
        actor, 
        enemy_coord: Coordinate, 
        component: AutonomousBehaviorComponent, 
        map_aggregate: PhysicalMapAggregate
    ) -> Optional[Coordinate]:
        """ターゲットから最も遠ざかる通行可能な座標を探す"""
        best_coord = None
        max_dist = actor.coordinate.euclidean_distance_to(enemy_coord)
        
        # 視界範囲の端あたりの座標をいくつかサンプリングする
        # (全タイルを走査するのは重いため、円周上の8方向+αを確認)
        r = component.vision_range
        curr = actor.coordinate
        
        samples = []
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            tx = int(curr.x + r * math.cos(rad))
            ty = int(curr.y + r * math.sin(rad))
            samples.append(Coordinate(tx, ty, curr.z))

        for sample in samples:
            # マップ外や通行不可は除外
            if not map_aggregate.is_passable(sample, component.capability):
                continue
            
            dist = sample.euclidean_distance_to(enemy_coord)
            if dist > max_dist:
                max_dist = dist
                best_coord = sample
                
        return best_coord

    def _calculate_return_move(self, actor, component, map_aggregate) -> Optional[Coordinate]:
        """初期位置へ戻る移動を計算"""
        if not component.initial_position:
            component.set_state(BehaviorStateEnum.IDLE)
            return None
            
        if actor.coordinate == component.initial_position:
            component.set_state(BehaviorStateEnum.IDLE)
            return None
            
        return self._get_next_step_to(actor, component.initial_position, map_aggregate, component)

    def _calculate_search_move(self, actor, component, map_aggregate) -> Optional[Coordinate]:
        """探索（最後に見失った場所へ向かい、周囲を探す）時の次の移動先を計算"""
        if not component.last_known_target_position:
            component.set_state(BehaviorStateEnum.RETURN)
            return self._calculate_return_move(actor, component, map_aggregate)

        # 目的地にまだ到達していないなら、そこへ向かう
        if actor.coordinate != component.last_known_target_position:
            return self._get_next_step_to(actor, component.last_known_target_position, map_aggregate, component)

        # 目的地に到達済み：周囲をランダムに探す
        if component.tick_search():
            # 探索終了、PATROL または RETURN へ遷移済み
            if component.state == BehaviorStateEnum.PATROL:
                return self._calculate_patrol_move(actor, component, map_aggregate)
            else:
                return self._calculate_return_move(actor, component, map_aggregate)

        # ランダムに方向を変える（見渡す）
        new_dir = random.choice([
            DirectionEnum.NORTH, DirectionEnum.SOUTH, 
            DirectionEnum.EAST, DirectionEnum.WEST
        ])
        component.turn(new_dir)

        # 設定された確率で1歩動く
        if random.random() < component.random_move_chance:
            # 隣接する通行可能なタイルを探す
            neighbors = []
            curr = actor.coordinate
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                neighbor = Coordinate(curr.x + dx, curr.y + dy, curr.z)
                if map_aggregate.is_passable(neighbor, component.capability):
                    neighbors.append(neighbor)
            
            if neighbors:
                return random.choice(neighbors)

        return None # その場で留まって見渡す

    def _calculate_patrol_move(self, actor, component, map_aggregate) -> Optional[Coordinate]:
        """巡回時の次の移動先を計算"""
        if not component.patrol_points:
            return None
        
        target_point = component.patrol_points[component.current_patrol_index]
        
        # 目的地に到達したか
        if actor.coordinate == target_point:
            component.current_patrol_index = (component.current_patrol_index + 1) % len(component.patrol_points)
            target_point = component.patrol_points[component.current_patrol_index]

        return self._get_next_step_to(actor, target_point, map_aggregate, component)

    def _get_next_step_to(self, actor, goal: Coordinate, map_aggregate: PhysicalMapAggregate, component: AutonomousBehaviorComponent) -> Optional[Coordinate]:
        """指定された目標への経路の次の1歩を取得する"""
        try:
            path = self._pathfinding_service.calculate_path(
                start=actor.coordinate,
                goal=goal,
                map_data=map_aggregate,
                capability=component.capability,
                allow_partial_path=True,
                smooth_path=False,
                exclude_object_id=actor.object_id
            )
            
            if len(path) > 1:
                component.on_move_success()
                return path[1] # [0]は現在地
            
            # 目的地に到達していないのに移動できない場合は失敗とみなす
            if actor.coordinate != goal:
                if component.on_move_failed():
                    map_aggregate.add_event(BehaviorStuckEvent.create(
                        aggregate_id=actor.object_id,
                        aggregate_type="Actor",
                        actor_id=actor.object_id,
                        state=component.state,
                        coordinate=actor.coordinate
                    ))
        except (PathNotFoundException, InvalidPathRequestException):
            if component.on_move_failed():
                map_aggregate.add_event(BehaviorStuckEvent.create(
                    aggregate_id=actor.object_id,
                    aggregate_type="Actor",
                    actor_id=actor.object_id,
                    state=component.state,
                    coordinate=actor.coordinate
                ))
            return None
            
        return None

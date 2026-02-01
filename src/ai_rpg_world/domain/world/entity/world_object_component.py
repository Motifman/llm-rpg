from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.exception import ValidationException
from ai_rpg_world.domain.world.exception.behavior_exception import (
    VisionRangeValidationException, 
    FOVAngleValidationException,
    SearchDurationValidationException,
    InvalidPatrolPointException,
    SearchDurationValidationException,
    HPPercentageValidationException,
    FleeThresholdValidationException,
    MaxFailuresValidationException
)


class WorldObjectComponent(ABC):
    """ワールドオブジェクトの機能を定義するコンポーネントの基底クラス"""
    
    @abstractmethod
    def get_type_name(self) -> str:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class ChestComponent(WorldObjectComponent):
    """宝箱の機能を持つコンポーネント"""
    def __init__(self, is_open: bool = False, item_ids: list[int] = None):
        self.is_open = is_open
        self.item_ids = item_ids or []

    def get_type_name(self) -> str:
        return "chest"

    def open(self):
        self.is_open = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_open": self.is_open,
            "item_ids": self.item_ids
        }


class DoorComponent(WorldObjectComponent):
    """ドアの機能を持つコンポーネント"""
    def __init__(self, is_open: bool = False, is_locked: bool = False):
        self.is_open = is_open
        self.is_locked = is_locked

    def get_type_name(self) -> str:
        return "door"

    def open(self):
        if self.is_locked:
            raise LockedDoorException("Door is locked")
        self.is_open = True

    def unlock(self):
        self.is_locked = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_open": self.is_open,
            "is_locked": self.is_locked
        }


class ActorComponent(WorldObjectComponent):
    """プレイヤーやNPCなどの動体（アクター）の機能を持つコンポーネント"""
    def __init__(
        self, 
        direction: DirectionEnum = DirectionEnum.SOUTH,
        capability: MovementCapability = None,
        owner_id: Optional[str] = None, # プレイヤーIDなど
        is_npc: bool = False,
        fov_angle: float = 360.0,
        race: str = "human",
        faction: str = "neutral"
    ):
        if not (0 <= fov_angle <= 360.0):
            raise FOVAngleValidationException(f"FOV angle must be between 0 and 360: {fov_angle}")
            
        self.direction = direction
        self.capability = capability or MovementCapability.normal_walk()
        self.owner_id = owner_id
        self.is_npc = is_npc
        self.fov_angle = fov_angle
        self.race = race
        self.faction = faction

    def get_type_name(self) -> str:
        return "actor"

    def turn(self, direction: DirectionEnum):
        self.direction = direction

    def update_capability(self, capability: MovementCapability):
        self.capability = capability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "speed_modifier": self.capability.speed_modifier,
            "capabilities": [c.value for c in self.capability.capabilities],
            "owner_id": self.owner_id,
            "is_npc": self.is_npc,
            "fov_angle": self.fov_angle,
            "race": self.race,
            "faction": self.faction
        }


class InteractableComponent(WorldObjectComponent):
    """インタラクション（調べる、話しかける等）が可能なコンポーネント"""
    def __init__(self, interaction_type: str, data: Dict[str, Any] = None):
        self.interaction_type = interaction_type
        self.data = data or {}

    def get_type_name(self) -> str:
        return "interactable"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interaction_type": self.interaction_type,
            "data": self.data
        }


class AutonomousBehaviorComponent(ActorComponent):
    """自律的な行動ロジックを持つアクターコンポーネント"""
    def __init__(
        self,
        direction: DirectionEnum = DirectionEnum.SOUTH,
        capability: MovementCapability = None,
        owner_id: Optional[str] = None,
        is_npc: bool = True,
        state: BehaviorStateEnum = BehaviorStateEnum.IDLE,
        vision_range: int = 5,
        fov_angle: float = 90.0,
        patrol_points: list[Coordinate] = None,
        search_duration: int = 3,
        race: str = "monster",
        faction: str = "enemy",
        hp_percentage: float = 1.0,
        flee_threshold: float = 0.2,
        max_failures: int = 3,
        initial_position: Optional[Coordinate] = None,
        random_move_chance: float = 0.5
    ):
        super().__init__(direction, capability, owner_id, is_npc, fov_angle, race, faction)
        self._validate(vision_range, search_duration, hp_percentage, flee_threshold, max_failures, random_move_chance)
            
        self.state = state
        self.vision_range = vision_range
        self.patrol_points = patrol_points or []
        
        self.current_patrol_index = 0
        self.target_id: Optional[WorldObjectId] = None
        self.last_known_target_position: Optional[Coordinate] = None
        self.search_duration = search_duration
        self.search_timer = 0
        
        # 逃走・諦め・HP・種族関連
        self.hp_percentage = hp_percentage
        self.flee_threshold = flee_threshold
        self.max_failures = max_failures
        self.failure_count = 0
        self.initial_position = initial_position
        self.random_move_chance = random_move_chance

    def _validate(self, vision_range, search_duration, hp_percentage, flee_threshold, max_failures, random_move_chance):
        if vision_range < 0:
            raise VisionRangeValidationException("Vision range cannot be negative")
        if search_duration < 0:
            raise SearchDurationValidationException("Search duration cannot be negative")
        if not (0.0 <= hp_percentage <= 1.0):
            raise HPPercentageValidationException("HP percentage must be between 0.0 and 1.0")
        if not (0.0 <= flee_threshold <= 1.0):
            raise FleeThresholdValidationException("Flee threshold must be between 0.0 and 1.0")
        if max_failures < 1:
            raise MaxFailuresValidationException("Max failures must be at least 1")
        if not (0.0 <= random_move_chance <= 1.0):
            # 汎用的なValidationExceptionまたは新設
            raise ValidationException(f"Random move chance must be between 0.0 and 1.0: {random_move_chance}")

    def get_type_name(self) -> str:
        return "autonomous_actor"

    def set_state(self, new_state: BehaviorStateEnum):
        if self.state == new_state:
            return
        self.state = new_state
        # 状態リセットロジック
        self.failure_count = 0
        if new_state not in [BehaviorStateEnum.SEARCH, BehaviorStateEnum.FLEE]:
            self.search_timer = 0
        if new_state != BehaviorStateEnum.CHASE and new_state != BehaviorStateEnum.FLEE:
            self.target_id = None

    def update_last_known_position(self, coordinate: Coordinate):
        self.last_known_target_position = coordinate

    def update_hp(self, hp_percentage: float):
        if not (0.0 <= hp_percentage <= 1.0):
            raise HPPercentageValidationException("HP percentage must be between 0.0 and 1.0")
        self.hp_percentage = hp_percentage

    def spot_target(self, target_id: WorldObjectId, coordinate: Coordinate):
        """ターゲットを捕捉した際の状態遷移"""
        self.target_id = target_id
        self.last_known_target_position = coordinate
        if self.hp_percentage <= self.flee_threshold:
            self.set_state(BehaviorStateEnum.FLEE)
        else:
            self.set_state(BehaviorStateEnum.CHASE)

    def lose_target(self):
        """ターゲットを見失った際の状態遷移"""
        if self.state == BehaviorStateEnum.CHASE:
            self.set_state(BehaviorStateEnum.SEARCH)
        elif self.state == BehaviorStateEnum.FLEE:
            # 逃走中に見失ったら帰還へ
            self.set_state(BehaviorStateEnum.RETURN)

    def on_move_success(self):
        self.failure_count = 0

    def on_move_failed(self):
        self.failure_count += 1
        if self.failure_count >= self.max_failures:
            self.set_state(BehaviorStateEnum.RETURN)
            self.failure_count = 0
            return True # スタックしたことを通知
        return False

    def tick_search(self):
        """探索タイマーを進め、終了したか返す"""
        self.search_timer += 1
        if self.search_timer >= self.search_duration:
            if self.patrol_points:
                self.set_state(BehaviorStateEnum.PATROL)
            else:
                self.set_state(BehaviorStateEnum.RETURN)
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "state": self.state.value,
            "vision_range": self.vision_range,
            "patrol_points": [{"x": p.x, "y": p.y, "z": p.z} for p in self.patrol_points],
            "target_id": str(self.target_id) if self.target_id else None,
            "last_known_target_position": {
                "x": self.last_known_target_position.x, 
                "y": self.last_known_target_position.y, 
                "z": self.last_known_target_position.z
            } if self.last_known_target_position else None,
            "search_duration": self.search_duration,
            "search_timer": self.search_timer,
            "hp_percentage": self.hp_percentage,
            "flee_threshold": self.flee_threshold,
            "max_failures": self.max_failures,
            "failure_count": self.failure_count,
            "initial_position": {
                "x": self.initial_position.x, 
                "y": self.initial_position.y, 
                "z": self.initial_position.z
            } if self.initial_position else None,
            "random_move_chance": self.random_move_chance
        })
        return data

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.exception import ValidationException, BusinessRuleException
if TYPE_CHECKING:
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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

    @property
    def capability(self) -> Optional[MovementCapability]:
        """移動能力を返す（デフォルトはNone）"""
        return None

    def turn(self, direction: DirectionEnum):
        """向きを変える（デフォルトは何もしない）"""
        pass

    @property
    def is_actor(self) -> bool:
        """アクターかどうか（デフォルトはFalse）"""
        return False

    @property
    def interaction_type(self) -> Optional[str]:
        """インタラクションタイプを返す（デフォルトはNone）"""
        return None

    @property
    def interaction_data(self) -> Dict[str, Any]:
        """インタラクションデータを返す（デフォルトは空辞書）"""
        return {}

    @property
    def interaction_duration(self) -> int:
        """インタラクションにかかるティック数（デフォルトは1）"""
        return 1


    @property
    def player_id(self) -> Optional["PlayerId"]:
        """紐付いているプレイヤーIDを返す（アクターでない場合はNone）"""
        return None

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
        player_id: Optional["PlayerId"] = None,
        is_npc: bool = False,
        fov_angle: float = 360.0,
        race: str = "human",
        faction: str = "neutral"
    ):
        if not (0 <= fov_angle <= 360.0):
            raise FOVAngleValidationException(f"FOV angle must be between 0 and 360: {fov_angle}")
            
        self.direction = direction
        self._capability = capability or MovementCapability.normal_walk()
        self._player_id = player_id
        self.is_npc = is_npc
        self.fov_angle = fov_angle
        self.race = race
        self.faction = faction

    @property
    def player_id(self) -> Optional["PlayerId"]:
        return self._player_id

    @property
    def capability(self) -> MovementCapability:
        return self._capability

    @property
    def is_actor(self) -> bool:
        return True

    def get_type_name(self) -> str:
        return "actor"

    def turn(self, direction: DirectionEnum):
        self.direction = direction

    def update_capability(self, capability: MovementCapability):
        self._capability = capability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "speed_modifier": self._capability.speed_modifier,
            "capabilities": [c.value for c in self._capability.capabilities],
            "player_id": str(self._player_id) if self._player_id else None,
            "is_npc": self.is_npc,
            "fov_angle": self.fov_angle,
            "race": self.race,
            "faction": self.faction
        }


class InteractableComponent(WorldObjectComponent):
    """インタラクション（調べる、話しかける等）が可能なコンポーネント"""
    def __init__(self, interaction_type: str, data: Dict[str, Any] = None, duration: int = 1):
        self._interaction_type = interaction_type
        self.data = data or {}
        self._duration = duration

    @property
    def interaction_type(self) -> str:
        return self._interaction_type

    @property
    def interaction_data(self) -> Dict[str, Any]:
        return self.data

    @property
    def interaction_duration(self) -> int:
        return self._duration

    def get_type_name(self) -> str:
        return "interactable"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interaction_type": self._interaction_type,
            "data": self.data
        }


class AutonomousBehaviorComponent(ActorComponent):
    """自律的な行動ロジックを持つアクターコンポーネント"""
    def __init__(
        self,
        direction: DirectionEnum = DirectionEnum.SOUTH,
        capability: MovementCapability = None,
        player_id: Optional["PlayerId"] = None,
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
        super().__init__(direction, capability, player_id, is_npc, fov_angle, race, faction)
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


from ai_rpg_world.domain.world.exception.harvest_exception import (
    HarvestQuantityValidationException,
    HarvestIntervalValidationException,
    ResourceExhaustedException,
    HarvestDomainException,
    HarvestInProgressException,
    HarvestNotStartedException
)


class HarvestableComponent(WorldObjectComponent):
    """
    採掘・採集可能な資源オブジェクトのコンポーネント。
    リソースの枯渇と時間経過による自動回復（Lazy Recovery）を管理する。
    """
    def __init__(
        self,
        loot_table_id: str,
        max_quantity: int = 1,
        respawn_interval: int = 100,
        initial_quantity: Optional[int] = None,
        last_harvest_tick: WorldTick = WorldTick(0),
        required_tool_category: Optional[str] = None,
        harvest_duration: int = 5,
        stamina_cost: int = 10
    ):
        self._validate_params(loot_table_id, max_quantity, respawn_interval, initial_quantity, harvest_duration, stamina_cost)
        self._loot_table_id = loot_table_id
        self._max_quantity = max_quantity
        self._respawn_interval = respawn_interval
        self._current_quantity = initial_quantity if initial_quantity is not None else max_quantity
        self._last_update_tick = last_harvest_tick
        self._required_tool_category = required_tool_category
        self._harvest_duration = harvest_duration
        self._stamina_cost = stamina_cost
        
        # 進行中の採取状態
        self._current_actor_id: Optional[WorldObjectId] = None
        self._harvest_finish_tick: Optional[WorldTick] = None

    def _validate_params(self, loot_table_id, max_quantity, respawn_interval, initial_quantity, harvest_duration, stamina_cost):
        if not loot_table_id:
            raise ValidationException("Loot table ID cannot be empty")
        if max_quantity <= 0:
            raise HarvestQuantityValidationException(f"Max quantity must be positive: {max_quantity}")
        if respawn_interval < 0:
            raise HarvestIntervalValidationException(f"Respawn interval cannot be negative: {respawn_interval}")
        if initial_quantity is not None:
            if initial_quantity < 0:
                raise HarvestQuantityValidationException(f"Initial quantity cannot be negative: {initial_quantity}")
            if initial_quantity > max_quantity:
                raise HarvestQuantityValidationException(
                    f"Initial quantity ({initial_quantity}) cannot exceed max quantity ({max_quantity})"
                )
        if harvest_duration < 0:
            raise ValidationException(f"Harvest duration cannot be negative: {harvest_duration}")
        if stamina_cost < 0:
            raise ValidationException(f"Stamina cost cannot be negative: {stamina_cost}")

    def get_type_name(self) -> str:
        return "harvestable"

    @property
    def loot_table_id(self) -> str:
        return self._loot_table_id

    @property
    def required_tool_category(self) -> Optional[str]:
        return self._required_tool_category

    @property
    def harvest_duration(self) -> int:
        return self._harvest_duration

    @property
    def interaction_duration(self) -> int:
        return self._harvest_duration

    @property
    def current_actor_id(self) -> Optional[WorldObjectId]:
        return self._current_actor_id

    def get_available_quantity(self, current_tick: WorldTick) -> int:
        """現在の利用可能な資源量を計算して返す（Lazy Recovery）"""
        if self._current_quantity >= self._max_quantity:
            return self._max_quantity
        
        elapsed = current_tick.value - self._last_update_tick.value
        if elapsed < 0:
            return self._current_quantity
            
        recovered = elapsed // self._respawn_interval
        return min(self._max_quantity, self._current_quantity + recovered)

    @property
    def stamina_cost(self) -> int:
        return self._stamina_cost

    def start_harvest(self, actor_id: WorldObjectId, current_tick: WorldTick) -> WorldTick:
        """採取アクションを開始する。終了ティックを返す。"""
        if self._current_actor_id is not None:
            raise HarvestInProgressException(f"Resource is already being harvested by {self._current_actor_id}")
        
        if self.get_available_quantity(current_tick) <= 0:
            raise ResourceExhaustedException("No resources available to harvest")
            
        self._current_actor_id = actor_id
        self._harvest_finish_tick = current_tick.add_duration(self._harvest_duration)
        return self._harvest_finish_tick

    def cancel_harvest(self, actor_id: WorldObjectId):
        """採取アクションを中断する"""
        if self._current_actor_id != actor_id:
            # 自分以外の採取を勝手にキャンセルすることはできない（例外にすべきか、単に無視すべきか）
            return
            
        self._current_actor_id = None
        self._harvest_finish_tick = None

    def is_harvest_complete(self, current_tick: WorldTick) -> bool:
        """採取が完了したか判定する"""
        if self._current_actor_id is None or self._harvest_finish_tick is None:
            return False
        return current_tick >= self._harvest_finish_tick

    def finish_harvest(self, actor_id: WorldObjectId, current_tick: WorldTick) -> bool:
        """採取アクションを完了させ、資源を減少させる。"""
        if self._current_actor_id != actor_id:
            raise HarvestNotStartedException("Actor is not harvesting this resource")
            
        if not self.is_harvest_complete(current_tick):
            # まだ完了していない
            return False
        
        available = self.get_available_quantity(current_tick)
        if available <= 0:
            # 採取中に他者に取られた、あるいは自然に消滅した場合
            self.cancel_harvest(actor_id)
            raise ResourceExhaustedException("Resource disappeared during harvest")

        # 資源減少
        self._current_quantity = available - 1
        self._last_update_tick = current_tick
        
        # 状態リセット
        self._current_actor_id = None
        self._harvest_finish_tick = None
        return True

    @property
    def interaction_type(self) -> str:
        return "harvest"

    @property
    def interaction_data(self) -> Dict[str, Any]:
        return {
            "loot_table_id": self._loot_table_id,
            "required_tool_category": self._required_tool_category
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loot_table_id": self._loot_table_id,
            "max_quantity": self._max_quantity,
            "current_quantity": self._current_quantity,
            "respawn_interval": self._respawn_interval,
            "last_update_tick": self._last_update_tick.value,
            "required_tool_category": self._required_tool_category,
            "stamina_cost": self._stamina_cost
        }

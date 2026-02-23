from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Set, TYPE_CHECKING, Union, List

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.pack_id import PackId
    from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.exception.map_exception import LockedDoorException, ItemAlreadyInChestException
from ai_rpg_world.domain.world.event.map_events import WorldObjectBlockingChangedEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    InteractionTypeEnum,
)
from ai_rpg_world.domain.monster.enum.monster_enum import (
    EcologyTypeEnum,
    ActiveTimeType,
)
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.exception import ValidationException, BusinessRuleException
if TYPE_CHECKING:
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy
from ai_rpg_world.domain.world.exception.behavior_exception import (
    VisionRangeValidationException,
    FOVAngleValidationException,
    InvalidPatrolPointException,
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
    def interaction_type(self) -> Optional[InteractionTypeEnum]:
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

    def apply_interaction_from(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        map_aggregate: "PhysicalMapAggregate",
        current_tick: WorldTick,
    ) -> None:
        """
        このオブジェクトがインタラクションされたときの効果を適用する。
        サブクラスでオーバーライドする。デフォルトは何もしない。
        """
        pass

    @property
    def player_id(self) -> Optional["PlayerId"]:
        """紐付いているプレイヤーIDを返す（アクターでない場合はNone）"""
        return None


class ChestComponent(WorldObjectComponent):
    """宝箱の機能を持つコンポーネント。

    開閉は interact_with(OPEN_CHEST) でトグル。
    収納・取得はアプリケーションサービス経由の Command（STORE_IN_CHEST / TAKE_FROM_CHEST）で行う。
    """
    def __init__(
        self,
        is_open: bool = False,
        item_ids: Optional[List[ItemInstanceId]] = None,
    ):
        self.is_open = is_open
        self._item_ids: List[ItemInstanceId] = list(item_ids) if item_ids else []

    @property
    def item_ids(self) -> List[ItemInstanceId]:
        """収納中のアイテムインスタンスIDリスト（不変として返すコピー）"""
        return list(self._item_ids)

    def get_type_name(self) -> str:
        return "chest"

    @property
    def interaction_type(self) -> Optional[InteractionTypeEnum]:
        """インタラクション種別: 開閉は OPEN_CHEST"""
        return InteractionTypeEnum.OPEN_CHEST

    @property
    def interaction_data(self) -> Dict[str, Any]:
        return {"is_open": self.is_open}

    @property
    def interaction_duration(self) -> int:
        return 1

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def toggle_open(self) -> None:
        self.is_open = not self.is_open

    def apply_interaction_from(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        map_aggregate: "PhysicalMapAggregate",
        current_tick: WorldTick,
    ) -> None:
        self.toggle_open()

    def add_item(self, item_instance_id: ItemInstanceId) -> None:
        if self.has_item(item_instance_id):
            raise ItemAlreadyInChestException(
                f"Item {item_instance_id} is already in this chest"
            )
        self._item_ids.append(item_instance_id)

    def remove_item(self, item_instance_id: ItemInstanceId) -> bool:
        """指定IDのアイテムを1件削除。存在すれば True、なければ False。"""
        for i, eid in enumerate(self._item_ids):
            if eid == item_instance_id:
                self._item_ids.pop(i)
                return True
        return False

    def has_item(self, item_instance_id: ItemInstanceId) -> bool:
        return any(eid == item_instance_id for eid in self._item_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_open": self.is_open,
            "item_ids": [eid.value for eid in self._item_ids],
        }


class DoorComponent(WorldObjectComponent):
    """ドアの機能を持つコンポーネント。開閉は interact_with(OPEN_DOOR) で行う。"""
    def __init__(self, is_open: bool = False, is_locked: bool = False):
        self.is_open = is_open
        self.is_locked = is_locked

    def get_type_name(self) -> str:
        return "door"

    @property
    def interaction_type(self) -> Optional[InteractionTypeEnum]:
        return InteractionTypeEnum.OPEN_DOOR

    @property
    def interaction_data(self) -> Dict[str, Any]:
        return {"is_open": self.is_open, "is_locked": self.is_locked}

    @property
    def interaction_duration(self) -> int:
        return 1

    def open(self) -> None:
        if self.is_locked:
            raise LockedDoorException("Door is locked")
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def toggle_open(self) -> None:
        if self.is_locked:
            raise LockedDoorException("Door is locked")
        self.is_open = not self.is_open

    def unlock(self) -> None:
        self.is_locked = False

    def apply_interaction_from(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        map_aggregate: "PhysicalMapAggregate",
        current_tick: WorldTick,
    ) -> None:
        self.toggle_open()
        target = map_aggregate.get_object(target_id)
        target.set_blocking(not self.is_open)
        map_aggregate.add_event(
            WorldObjectBlockingChangedEvent.create(
                aggregate_id=target_id,
                aggregate_type="WorldObject",
                object_id=target_id,
                is_blocking=target.is_blocking,
            )
        )

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
        faction: str = "neutral",
        pack_id: Optional["PackId"] = None,
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
        self.pack_id = pack_id

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
            "faction": self.faction,
            "pack_id": self.pack_id.value if self.pack_id else None,
        }


class InteractableComponent(WorldObjectComponent):
    """インタラクション（調べる、話しかける等）が可能なコンポーネント"""
    def __init__(
        self,
        interaction_type: Union[InteractionTypeEnum, str],
        data: Dict[str, Any] = None,
        duration: int = 1,
    ):
        if isinstance(interaction_type, str):
            self._interaction_type = InteractionTypeEnum(interaction_type)
        else:
            self._interaction_type = interaction_type
        self.data = data or {}
        self._duration = duration

    @property
    def interaction_type(self) -> InteractionTypeEnum:
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
            "interaction_type": self._interaction_type.value,
            "data": self.data
        }


from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo


class AutonomousBehaviorComponent(ActorComponent):
    """
    自律的な行動ロジックを持つアクターのマップ用コンポーネント（軽量版）。
    表示・パス探索・観測に必要なテンプレート由来の情報のみを保持する。
    行動状態（state, target_id 等）は Monster 集約が保持し、このコンポーネントには持たない。
    """
    def __init__(
        self,
        direction: DirectionEnum = DirectionEnum.SOUTH,
        capability: MovementCapability = None,
        player_id: Optional["PlayerId"] = None,
        is_npc: bool = True,
        vision_range: int = 5,
        fov_angle: float = 90.0,
        patrol_points: list[Coordinate] = None,
        race: str = "monster",
        faction: str = "enemy",
        initial_position: Optional[Coordinate] = None,
        random_move_chance: float = 0.5,
        available_skills: list[MonsterSkillInfo] = None,
        behavior_strategy_type: str = "default",
        pack_id: Optional["PackId"] = None,
        is_pack_leader: bool = False,
        ecology_type: EcologyTypeEnum = EcologyTypeEnum.NORMAL,
        ambush_chase_range: Optional[int] = None,
        territory_radius: Optional[int] = None,
        aggro_memory_policy: Optional[AggroMemoryPolicy] = None,
        active_time: ActiveTimeType = ActiveTimeType.ALWAYS,
        threat_races: Optional[Set[str]] = None,
        prey_races: Optional[Set[str]] = None,
    ):
        super().__init__(direction, capability, player_id, is_npc, fov_angle, race, faction, pack_id)
        self._validate(vision_range, random_move_chance)
        self.vision_range = vision_range
        self.patrol_points = patrol_points or []
        self.initial_position = initial_position
        self.random_move_chance = random_move_chance
        self.available_skills = available_skills or []
        self.behavior_strategy_type = behavior_strategy_type
        self.is_pack_leader = is_pack_leader
        self.ecology_type = ecology_type
        self.ambush_chase_range = ambush_chase_range
        self.territory_radius = territory_radius
        self.aggro_memory_policy = aggro_memory_policy
        self.active_time = active_time
        self.threat_races = threat_races or frozenset()
        self.prey_races = prey_races or frozenset()

    def _validate(self, vision_range: int, random_move_chance: float) -> None:
        if vision_range < 0:
            raise VisionRangeValidationException("Vision range cannot be negative")
        if not (0.0 <= random_move_chance <= 1.0):
            raise ValidationException(
                f"Random move chance must be between 0.0 and 1.0: {random_move_chance}"
            )

    def get_type_name(self) -> str:
        return "autonomous_actor"

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "vision_range": self.vision_range,
            "patrol_points": [{"x": p.x, "y": p.y, "z": p.z} for p in self.patrol_points],
            "initial_position": (
                {"x": self.initial_position.x, "y": self.initial_position.y, "z": self.initial_position.z}
                if self.initial_position else None
            ),
            "random_move_chance": self.random_move_chance,
            "behavior_strategy_type": self.behavior_strategy_type,
            "is_pack_leader": self.is_pack_leader,
            "ecology_type": self.ecology_type.value,
            "ambush_chase_range": self.ambush_chase_range,
            "territory_radius": self.territory_radius,
            "active_time": self.active_time.value,
            "threat_races": list(self.threat_races),
            "prey_races": list(self.prey_races),
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
    def interaction_type(self) -> InteractionTypeEnum:
        return InteractionTypeEnum.HARVEST

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

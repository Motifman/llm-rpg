import random
from typing import Optional
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterCreatedEvent,
    MonsterSpawnedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterRespawnedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
    MonsterAlreadySpawnedException,
    MonsterNotDeadException,
    MonsterNotSpawnedException,
    MonsterRespawnIntervalNotMetException,
    MonsterInsufficientMpException
)
from ai_rpg_world.domain.monster.service.monster_combat_service import MonsterCombatService
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick


class MonsterAggregate(AggregateRoot):
    """モンスター個体の集約ルート"""

    def __init__(
        self,
        monster_id: MonsterId,
        template: MonsterTemplate,
        world_object_id: WorldObjectId,
        hp: Optional[MonsterHp] = None,
        mp: Optional[MonsterMp] = None,
        status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
        last_death_tick: Optional[WorldTick] = None,
        coordinate: Optional[Coordinate] = None,
    ):
        super().__init__()
        self._monster_id = monster_id
        self._template = template
        self._world_object_id = world_object_id
        self._hp = hp or MonsterHp.create(template.base_stats.max_hp, template.base_stats.max_hp)
        self._mp = mp or MonsterMp.create(template.base_stats.max_mp, template.base_stats.max_mp)
        self._status = status
        self._last_death_tick = last_death_tick
        self._coordinate = coordinate

    @classmethod
    def create(
        cls,
        monster_id: MonsterId,
        template: MonsterTemplate,
        world_object_id: WorldObjectId
    ) -> "MonsterAggregate":
        """モンスター個体を新規作成する（初期状態は未出現）"""
        monster = cls(
            monster_id=monster_id,
            template=template,
            world_object_id=world_object_id,
            status=MonsterStatusEnum.DEAD,  # 初期状態はDEAD（出現前）とする
            coordinate=None
        )
        monster.add_event(MonsterCreatedEvent.create(
            aggregate_id=monster_id,
            aggregate_type="MonsterAggregate",
            template_id=template.template_id.value
        ))
        return monster

    @property
    def monster_id(self) -> MonsterId:
        return self._monster_id

    @property
    def template(self) -> MonsterTemplate:
        return self._template

    @property
    def world_object_id(self) -> WorldObjectId:
        return self._world_object_id

    @property
    def hp(self) -> MonsterHp:
        return self._hp

    @property
    def mp(self) -> MonsterMp:
        return self._mp

    @property
    def status(self) -> MonsterStatusEnum:
        return self._status

    @property
    def last_death_tick(self) -> Optional[WorldTick]:
        return self._last_death_tick

    @property
    def coordinate(self) -> Optional[Coordinate]:
        return self._coordinate

    def _initialize_status(self, coordinate: Coordinate):
        """ステータスを初期化（出現/リスポーン時）"""
        self._coordinate = coordinate
        self._status = MonsterStatusEnum.ALIVE
        self._hp = MonsterHp.create(self._template.base_stats.max_hp, self._template.base_stats.max_hp)
        self._mp = MonsterMp.create(self._template.base_stats.max_mp, self._template.base_stats.max_mp)
        self._last_death_tick = None

    def spawn(self, coordinate: Coordinate):
        """モンスターを出現させる"""
        if self._coordinate is not None or self._status == MonsterStatusEnum.ALIVE:
            raise MonsterAlreadySpawnedException(f"Monster {self._monster_id} is already spawned at {self._coordinate}")

        self._initialize_status(coordinate)
        
        self.add_event(MonsterSpawnedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": coordinate.x, "y": coordinate.y, "z": coordinate.z}
        ))

    def take_damage(self, raw_damage: int, current_tick: WorldTick):
        """ダメージを受ける"""
        if self._status != MonsterStatusEnum.ALIVE:
            if self._status == MonsterStatusEnum.DEAD and self._last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")

        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        # 戦闘サービスを使用してダメージ計算と回避判定を行う
        result = MonsterCombatService.calculate_damage(self, raw_damage)

        if result.is_evaded:
            self.add_event(MonsterEvadedEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate"
            ))
            return

        actual_damage = result.damage
        self._hp = self._hp.damage(actual_damage)
        
        self.add_event(MonsterDamagedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            damage=actual_damage,
            current_hp=self._hp.value
        ))

        if not self._hp.is_alive():
            self._die(current_tick)

    def heal_hp(self, amount: int):
        """HPを回復する"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        old_hp = self._hp.value
        self._hp = self._hp.heal(amount)
        actual_healed = self._hp.value - old_hp

        if actual_healed > 0:
            self.add_event(MonsterHealedEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                amount=actual_healed,
                current_hp=self._hp.value
            ))

    def recover_mp(self, amount: int):
        """MPを回復する"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        old_mp = self._mp.value
        self._mp = self._mp.recover(amount)
        actual_recovered = self._mp.value - old_mp

        if actual_recovered > 0:
            self.add_event(MonsterMpRecoveredEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                amount=actual_recovered,
                current_mp=self._mp.value
            ))

    def use_mp(self, amount: int):
        """MPを消費する"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        # MonsterMp.use 内で MonsterInsufficientMpException が投げられる
        self._mp = self._mp.use(amount)

    def on_tick(self, current_tick: WorldTick):
        """時間経過による処理（自然回復など）"""
        if self._status == MonsterStatusEnum.ALIVE:
            # 微量回復（例：最大値の1%）
            hp_regen = max(1, self._template.base_stats.max_hp // 100)
            mp_regen = max(1, self._template.base_stats.max_mp // 100)
            
            self.heal_hp(hp_regen)
            self.recover_mp(mp_regen)
        
        # リスポーン判定などは上位のアプリケーションサービスで行うことを想定するが、
        # 必要に応じてここでもロジックを追加できる

    def _die(self, current_tick: WorldTick):
        """死亡する（内部用）"""
        if self._status == MonsterStatusEnum.DEAD:
            return

        self._status = MonsterStatusEnum.DEAD
        self._last_death_tick = current_tick
        self._coordinate = None  # 死亡時は座標をクリア
        
        respawn_tick = current_tick.value + self._template.respawn_info.respawn_interval_ticks
        
        self.add_event(MonsterDiedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=respawn_tick,
            exp=self._template.reward_info.exp,
            gold=self._template.reward_info.gold,
            loot_table_id=self._template.reward_info.loot_table_id
        ))

    def should_respawn(self, current_tick: WorldTick) -> bool:
        """リスポーンすべきか判定する"""
        if self._status != MonsterStatusEnum.DEAD:
            return False
        
        if not self._template.respawn_info.is_auto_respawn:
            return False

        if self._last_death_tick is None:
            return True

        elapsed = current_tick.value - self._last_death_tick.value
        return elapsed >= self._template.respawn_info.respawn_interval_ticks

    def respawn(self, coordinate: Coordinate, current_tick: WorldTick):
        """リスポーンさせる"""
        if self._status != MonsterStatusEnum.DEAD:
            raise MonsterNotDeadException(f"Monster {self._monster_id} is not dead, cannot respawn")

        if not self.should_respawn(current_tick):
            raise MonsterRespawnIntervalNotMetException(
                f"Monster {self._monster_id} cannot respawn yet. "
                f"Last death: {self._last_death_tick.value if self._last_death_tick else 'None'}, "
                f"Current tick: {current_tick.value}"
            )

        self._initialize_status(coordinate)

        self.add_event(MonsterRespawnedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": coordinate.x, "y": coordinate.y, "z": coordinate.z}
        ))


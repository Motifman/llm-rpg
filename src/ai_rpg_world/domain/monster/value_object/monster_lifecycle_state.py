"""
MonsterLifecycleState: HP/MP・生死・成長基点・飢餓を集約する不変の値オブジェクト。

MonsterAggregate のライフサイクル関連の状態を保持し、変更時は常に新しいインスタンスを返す。
テンプレートへの依存は避け、飢餓のルール（閾値等）はメソッド引数で受け取る。
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
)


@dataclass(frozen=True)
class MonsterLifecycleState:
    """
    モンスターのライフサイクル状態（HP/MP・生死・成長基点・飢餓）。
    不変の値オブジェクト。変更時は新しいインスタンスを返す。
    """

    hp: MonsterHp
    mp: MonsterMp
    status: MonsterStatusEnum
    last_death_tick: Optional[WorldTick]
    spawned_at_tick: Optional[WorldTick]
    hunger: float
    starvation_timer: int

    def __post_init__(self) -> None:
        if not (0.0 <= self.hunger <= 1.0):
            raise MonsterStatsValidationException(
                f"hunger must be between 0.0 and 1.0: {self.hunger}"
            )
        if self.starvation_timer < 0:
            raise MonsterStatsValidationException(
                f"starvation_timer cannot be negative: {self.starvation_timer}"
            )

    @classmethod
    def create_for_unspawned(
        cls,
        max_hp: int,
        max_mp: int,
    ) -> "MonsterLifecycleState":
        """
        未出現のモンスター用の初期状態を作成する。
        status=DEAD, last_death_tick=None（未スポーンを示す）, spawned_at_tick=None。
        """
        hp = MonsterHp.create(max_hp, max_hp)
        mp = MonsterMp.create(max_mp, max_mp)
        return cls(
            hp=hp,
            mp=mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=None,
            spawned_at_tick=None,
            hunger=0.0,
            starvation_timer=0,
        )

    @classmethod
    def create_for_spawned(
        cls,
        max_hp: int,
        max_mp: int,
        spawned_at_tick: WorldTick,
        initial_hunger: float = 0.0,
    ) -> "MonsterLifecycleState":
        """
        スポーン/リスポーン時の状態を作成する。
        HP/MP 満タン、status=ALIVE、飢餓リセット。
        """
        hp = MonsterHp.create(max_hp, max_hp)
        mp = MonsterMp.create(max_mp, max_mp)
        hunger = max(0.0, min(1.0, initial_hunger))
        return cls(
            hp=hp,
            mp=mp,
            status=MonsterStatusEnum.ALIVE,
            last_death_tick=None,
            spawned_at_tick=spawned_at_tick,
            hunger=hunger,
            starvation_timer=0,
        )

    def apply_damage(self, amount: int) -> "MonsterLifecycleState":
        """ダメージを適用した新しい状態を返す。"""
        if amount < 0:
            raise MonsterStatsValidationException(
                f"Damage amount cannot be negative: {amount}"
            )
        new_hp = self.hp.damage(amount)
        return MonsterLifecycleState(
            hp=new_hp,
            mp=self.mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=self.hunger,
            starvation_timer=self.starvation_timer,
        )

    def apply_heal(self, amount: int) -> "MonsterLifecycleState":
        """HP 回復を適用した新しい状態を返す。"""
        if amount < 0:
            raise MonsterStatsValidationException(
                f"Heal amount cannot be negative: {amount}"
            )
        new_hp = self.hp.heal(amount)
        return MonsterLifecycleState(
            hp=new_hp,
            mp=self.mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=self.hunger,
            starvation_timer=self.starvation_timer,
        )

    def apply_mp_recovery(self, amount: int) -> "MonsterLifecycleState":
        """MP 回復を適用した新しい状態を返す。"""
        if amount < 0:
            raise MonsterStatsValidationException(
                f"Recover amount cannot be negative: {amount}"
            )
        new_mp = self.mp.recover(amount)
        return MonsterLifecycleState(
            hp=self.hp,
            mp=new_mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=self.hunger,
            starvation_timer=self.starvation_timer,
        )

    def apply_mp_use(self, amount: int) -> "MonsterLifecycleState":
        """MP 消費を適用した新しい状態を返す。"""
        new_mp = self.mp.use(amount)
        return MonsterLifecycleState(
            hp=self.hp,
            mp=new_mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=self.hunger,
            starvation_timer=self.starvation_timer,
        )

    def with_death(self, current_tick: WorldTick) -> "MonsterLifecycleState":
        """死亡状態にした新しい状態を返す。"""
        return MonsterLifecycleState(
            hp=self.hp,
            mp=self.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=current_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=self.hunger,
            starvation_timer=self.starvation_timer,
        )

    def with_spawn_reset(
        self,
        max_hp: int,
        max_mp: int,
        spawned_at_tick: WorldTick,
        initial_hunger: float = 0.0,
    ) -> "MonsterLifecycleState":
        """スポーン/リスポーン時のリセットを適用した新しい状態を返す。"""
        return MonsterLifecycleState.create_for_spawned(
            max_hp=max_hp,
            max_mp=max_mp,
            spawned_at_tick=spawned_at_tick,
            initial_hunger=initial_hunger,
        )

    def tick_hunger(
        self,
        hunger_increase_per_tick: float,
        hunger_starvation_threshold: float,
        starvation_ticks: int,
    ) -> Tuple["MonsterLifecycleState", bool]:
        """
        1 tick 分の飢餓を適用し、(新しい状態, 飢餓死すべきか) を返す。

        引数バリデーション:
        - starvation_ticks < 0, hunger_increase_per_tick < 0,
          hunger_starvation_threshold が [0, 1] 外: 例外を送出する（設定ミスを早期発見）。
        - starvation_ticks == 0 または hunger_increase_per_tick == 0: 飢餓無効として (self, False) を返す。
        """
        if starvation_ticks < 0:
            raise MonsterStatsValidationException(
                f"starvation_ticks cannot be negative: {starvation_ticks}"
            )
        if hunger_increase_per_tick < 0:
            raise MonsterStatsValidationException(
                f"hunger_increase_per_tick cannot be negative: {hunger_increase_per_tick}"
            )
        if not (0.0 <= hunger_starvation_threshold <= 1.0):
            raise MonsterStatsValidationException(
                f"hunger_starvation_threshold must be between 0.0 and 1.0: {hunger_starvation_threshold}"
            )
        if starvation_ticks == 0 or hunger_increase_per_tick == 0:
            return (self, False)

        new_hunger = min(1.0, self.hunger + hunger_increase_per_tick)
        if new_hunger >= hunger_starvation_threshold:
            new_timer = self.starvation_timer + 1
            should_starve = new_timer >= starvation_ticks
        else:
            new_timer = 0
            should_starve = False

        new_state = MonsterLifecycleState(
            hp=self.hp,
            mp=self.mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=new_hunger,
            starvation_timer=new_timer,
        )
        return (new_state, should_starve)

    def decrease_hunger(self, amount: float) -> "MonsterLifecycleState":
        """
        飢餓を減少させた新しい状態を返す。
        獲物撃破・採食時に使用。amount <= 0 のときは現状のまま返す。
        """
        if amount <= 0:
            return self
        new_hunger = max(0.0, min(1.0, self.hunger - amount))
        return MonsterLifecycleState(
            hp=self.hp,
            mp=self.mp,
            status=self.status,
            last_death_tick=self.last_death_tick,
            spawned_at_tick=self.spawned_at_tick,
            hunger=new_hunger,
            starvation_timer=0,
        )

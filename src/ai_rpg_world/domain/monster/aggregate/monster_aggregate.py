from typing import Optional, List, TYPE_CHECKING
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum, DeathCauseEnum
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterCreatedEvent,
    MonsterSpawnedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterRespawnedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDecidedToInteractEvent,
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
    MonsterAlreadySpawnedException,
    MonsterNotDeadException,
    MonsterNotSpawnedException,
    MonsterRespawnIntervalNotMetException
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, EcologyTypeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot
from ai_rpg_world.domain.monster.service.monster_config_service import MonsterConfigService, DefaultMonsterConfigService
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    BehaviorStateTransitionService,
    StateTransitionResult,
)
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.pack_id import PackId
    from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
    from ai_rpg_world.domain.monster.action_resolver import IMonsterActionResolver


class MonsterAggregate(AggregateRoot):
    """モンスター個体の集約ルート"""

    def __init__(
        self,
        monster_id: MonsterId,
        template: MonsterTemplate,
        world_object_id: WorldObjectId,
        skill_loadout: SkillLoadoutAggregate,
        hp: Optional[MonsterHp] = None,
        mp: Optional[MonsterMp] = None,
        status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
        last_death_tick: Optional[WorldTick] = None,
        coordinate: Optional[Coordinate] = None,
        spot_id: Optional[SpotId] = None,
        active_effects: List[StatusEffect] = None,
        pack_id: Optional["PackId"] = None,
        is_pack_leader: bool = False,
        initial_spawn_coordinate: Optional[Coordinate] = None,
        spawned_at_tick: Optional[WorldTick] = None,
        behavior_state: BehaviorStateEnum = BehaviorStateEnum.IDLE,
        behavior_target_id: Optional[WorldObjectId] = None,
        behavior_last_known_position: Optional[Coordinate] = None,
        behavior_initial_position: Optional[Coordinate] = None,
        behavior_patrol_index: int = 0,
        behavior_search_timer: int = 0,
        behavior_failure_count: int = 0,
        hunger: float = 0.0,
        starvation_timer: int = 0,
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
        self._spot_id = spot_id
        self._active_effects = active_effects or []
        self._skill_loadout = skill_loadout
        self._pack_id = pack_id
        self._is_pack_leader = is_pack_leader
        self._initial_spawn_coordinate = initial_spawn_coordinate
        self._spawned_at_tick = spawned_at_tick
        self._behavior_state = behavior_state
        self._behavior_target_id = behavior_target_id
        self._behavior_last_known_position = behavior_last_known_position
        self._behavior_initial_position = behavior_initial_position
        self._behavior_patrol_index = behavior_patrol_index
        self._behavior_search_timer = behavior_search_timer
        self._behavior_failure_count = behavior_failure_count
        self._hunger = max(0.0, min(1.0, hunger))
        self._starvation_timer = max(0, starvation_timer)

    @classmethod
    def create(
        cls,
        monster_id: MonsterId,
        template: MonsterTemplate,
        world_object_id: WorldObjectId,
        skill_loadout: SkillLoadoutAggregate,
    ) -> "MonsterAggregate":
        """モンスター個体を新規作成する（初期状態は未出現）"""
        monster = cls(
            monster_id=monster_id,
            template=template,
            world_object_id=world_object_id,
            status=MonsterStatusEnum.DEAD,  # 初期状態はDEAD（出現前）とする
            coordinate=None,
            skill_loadout=skill_loadout,
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

    def _get_current_growth_stage(self, current_tick: WorldTick) -> Optional[GrowthStage]:
        """現在の成長段階を返す。未スポーンまたは段階なしの場合は None。"""
        if self._spawned_at_tick is None:
            return None
        stages = self._template.growth_stages
        if not stages:
            return None
        elapsed = current_tick.value - self._spawned_at_tick.value
        if elapsed < 0:
            return None
        stage = None
        for g in stages:
            if elapsed >= g.after_ticks:
                stage = g
        return stage

    def get_current_growth_multiplier(self, current_tick: WorldTick) -> float:
        """
        現在の成長段階に応じたステータス乗率を返す。
        spawned_at_tick が未設定または growth_stages が空の場合は 1.0。
        """
        stage = self._get_current_growth_stage(current_tick)
        return stage.stats_multiplier if stage else 1.0

    def get_effective_flee_threshold(self, current_tick: WorldTick) -> float:
        """
        現在の成長段階を反映した FLEE 閾値を返す。
        テンプレートの flee_threshold に flee_bias_multiplier を掛ける（未指定時は 1.0）。
        """
        base = self._template.flee_threshold
        stage = self._get_current_growth_stage(current_tick)
        if stage is None or stage.flee_bias_multiplier is None:
            return base
        return min(1.0, round(base * stage.flee_bias_multiplier, 4))

    def get_allow_chase(self, current_tick: WorldTick) -> bool:
        """現在の成長段階で CHASE（追跡）を許可するか。"""
        stage = self._get_current_growth_stage(current_tick)
        return stage.allow_chase if stage else True

    def get_effective_stats(self, current_tick: WorldTick) -> BaseStats:
        """バフ・デバフ・成長段階適用後の実効ステータス（期限切れを除外）"""
        # 期限切れエフェクトのクリーンアップ
        self.cleanup_expired_effects(current_tick)
        
        base = self._template.base_stats
        growth_mult = self.get_current_growth_multiplier(current_tick)
        atk_mult = growth_mult
        def_mult = growth_mult
        spd_mult = growth_mult
        
        for effect in self._active_effects:
            if effect.effect_type == StatusEffectType.ATTACK_UP:
                atk_mult *= effect.value
            elif effect.effect_type == StatusEffectType.ATTACK_DOWN:
                atk_mult *= effect.value
            elif effect.effect_type == StatusEffectType.DEFENSE_UP:
                def_mult *= effect.value
            elif effect.effect_type == StatusEffectType.DEFENSE_DOWN:
                def_mult *= effect.value
            elif effect.effect_type == StatusEffectType.SPEED_UP:
                spd_mult *= effect.value
            elif effect.effect_type == StatusEffectType.SPEED_DOWN:
                spd_mult *= effect.value
                
        return BaseStats(
            max_hp=max(1, int(base.max_hp * growth_mult)),
            max_mp=max(1, int(base.max_mp * growth_mult)),
            attack=int(base.attack * atk_mult),
            defense=int(base.defense * def_mult),
            speed=int(base.speed * spd_mult),
            critical_rate=base.critical_rate,
            evasion_rate=base.evasion_rate,
        )

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

    @property
    def spot_id(self) -> Optional[SpotId]:
        return self._spot_id

    @property
    def skill_loadout(self) -> SkillLoadoutAggregate:
        return self._skill_loadout

    @property
    def pack_id(self) -> Optional["PackId"]:
        return self._pack_id

    @property
    def is_pack_leader(self) -> bool:
        return self._is_pack_leader

    @property
    def spawned_at_tick(self) -> Optional[WorldTick]:
        return self._spawned_at_tick

    @property
    def behavior_state(self) -> BehaviorStateEnum:
        return self._behavior_state

    @property
    def behavior_target_id(self) -> Optional[WorldObjectId]:
        return self._behavior_target_id

    @property
    def behavior_last_known_position(self) -> Optional[Coordinate]:
        return self._behavior_last_known_position

    @property
    def behavior_initial_position(self) -> Optional[Coordinate]:
        return self._behavior_initial_position

    @property
    def behavior_patrol_index(self) -> int:
        return self._behavior_patrol_index

    @property
    def behavior_search_timer(self) -> int:
        return self._behavior_search_timer

    @property
    def behavior_failure_count(self) -> int:
        return self._behavior_failure_count

    def advance_patrol_index(self, patrol_points_count: int) -> None:
        """パトロール点に到達したときにインデックスを進める。patrol_points_count は点の数。"""
        if patrol_points_count <= 0:
            return
        self._behavior_patrol_index = (
            self._behavior_patrol_index + 1
        ) % patrol_points_count

    def _initialize_status(
        self,
        coordinate: Coordinate,
        spot_id: SpotId,
        current_tick: WorldTick,
        initial_hunger: float = 0.0,
    ) -> None:
        """
        ステータスを初期化（出現/リスポーン時）。
        呼び出し元で _spawned_at_tick を current_tick に設定したうえで呼ぶこと。
        HP/MP は実効ステータスで満タンに初期化。行動状態・飢餓もリセット（initial_hunger で指定可能）。
        """
        self._coordinate = coordinate
        self._spot_id = spot_id
        self._status = MonsterStatusEnum.ALIVE
        effective = self.get_effective_stats(current_tick)
        self._hp = MonsterHp.create(effective.max_hp, effective.max_hp)
        self._mp = MonsterMp.create(effective.max_mp, effective.max_mp)
        self._last_death_tick = None
        self._behavior_initial_position = coordinate
        self._behavior_state = BehaviorStateEnum.IDLE
        self._behavior_target_id = None
        self._behavior_last_known_position = None
        self._behavior_patrol_index = 0
        self._behavior_search_timer = 0
        self._behavior_failure_count = 0
        self._hunger = max(0.0, min(1.0, initial_hunger))
        self._starvation_timer = 0

    @property
    def hunger(self) -> float:
        """現在の飢餓値（0.0〜1.0）。"""
        return self._hunger

    def update_map_placement(self, spot_id: SpotId, coordinate: Coordinate) -> None:
        """ゲートウェイ等によるマップ間移動時に座標・スポットを更新する（ALIVE時のみ想定）"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        self._coordinate = coordinate
        self._spot_id = spot_id

    def spawn(
        self,
        coordinate: Coordinate,
        spot_id: SpotId,
        current_tick: WorldTick,
        pack_id: Optional["PackId"] = None,
        is_pack_leader: bool = False,
        initial_hunger: float = 0.0,
    ):
        """モンスターを出現させる。pack_id / is_pack_leader はインスタンス単位で設定する。"""
        if self._coordinate is not None or self._status == MonsterStatusEnum.ALIVE:
            raise MonsterAlreadySpawnedException(f"Monster {self._monster_id} is already spawned at {self._coordinate}")

        self._spawned_at_tick = current_tick
        self._initialize_status(coordinate, spot_id, current_tick, initial_hunger=initial_hunger)
        self._pack_id = pack_id
        self._is_pack_leader = is_pack_leader
        self._initial_spawn_coordinate = coordinate

        self.add_event(MonsterSpawnedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": coordinate.x, "y": coordinate.y, "z": coordinate.z},
            spot_id=spot_id,
        ))

    def apply_damage(self, final_damage: int, current_tick: WorldTick, attacker_id: Optional[WorldObjectId] = None, killer_player_id: Optional[PlayerId] = None):
        """計算済みのダメージを適用する"""
        if self._status != MonsterStatusEnum.ALIVE:
            if self._status == MonsterStatusEnum.DEAD and self._last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")

        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        self._hp = self._hp.damage(final_damage)
        
        self.add_event(MonsterDamagedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            damage=final_damage,
            current_hp=self._hp.value,
            attacker_id=attacker_id
        ))

        if not self._hp.is_alive():
            cause = DeathCauseEnum.KILLED_BY_PLAYER if killer_player_id else DeathCauseEnum.KILLED_BY_MONSTER
            self._die(
                current_tick,
                killer_player_id=killer_player_id,
                killer_world_object_id=attacker_id,
                cause=cause if (killer_player_id or attacker_id) else None,
            )

    def record_evasion(self):
        """回避を記録する（ALIVE時のみ）"""
        if self._status != MonsterStatusEnum.ALIVE:
            if self._status == MonsterStatusEnum.DEAD and self._last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")

        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        self.add_event(MonsterEvadedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": self._coordinate.x, "y": self._coordinate.y, "z": self._coordinate.z},
            current_hp=self._hp.value,
        ))

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

    def on_tick(self, current_tick: WorldTick, config: MonsterConfigService = DefaultMonsterConfigService()):
        """時間経過による処理（自然回復など）。自然回復量は実効ステータス（成長段階反映後）の max_hp/max_mp を基準とする。"""
        if self._status == MonsterStatusEnum.ALIVE:
            effective = self.get_effective_stats(current_tick)
            regen_rate = config.get_regeneration_rate()
            hp_regen = max(1, int(effective.max_hp * regen_rate))
            mp_regen = max(1, int(effective.max_mp * regen_rate))
            self.heal_hp(hp_regen)
            self.recover_mp(mp_regen)
        
        # リスポーン判定などは上位のアプリケーションサービスで行うことを想定するが、
        # 必要に応じてここでもロジックを追加できる

    def _die(
        self,
        current_tick: WorldTick,
        killer_player_id: Optional[PlayerId] = None,
        killer_world_object_id: Optional[WorldObjectId] = None,
        cause: Optional[DeathCauseEnum] = None,
    ) -> None:
        """死亡する（内部用）"""
        if self._status == MonsterStatusEnum.DEAD:
            return

        self._status = MonsterStatusEnum.DEAD
        self._last_death_tick = current_tick
        spot_id_for_event = self._spot_id
        self._coordinate = None  # 死亡時は座標をクリア（spot_id はリスポーン判定のため保持）

        respawn_tick = current_tick.value + self._template.respawn_info.respawn_interval_ticks

        self.add_event(MonsterDiedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=respawn_tick,
            exp=self._template.reward_info.exp,
            gold=self._template.reward_info.gold,
            loot_table_id=self._template.reward_info.loot_table_id,
            killer_player_id=killer_player_id,
            killer_world_object_id=killer_world_object_id,
            cause=cause,
            spot_id=spot_id_for_event,
        ))

    def starve(self, current_tick: WorldTick) -> None:
        """飢餓で死亡させる。ALIVE のときのみ有効。"""
        if self._status != MonsterStatusEnum.ALIVE:
            if self._status == MonsterStatusEnum.DEAD and self._last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
        self._die(current_tick, cause=DeathCauseEnum.STARVATION)

    def tick_hunger(self, current_tick: WorldTick) -> bool:
        """
        1 tick 分の飢餓を適用し、飢餓死すべきか返す。
        飢餓が無効（template.starvation_ticks <= 0）の場合は False。
        ALIVE かつスポーン済みのときのみ有効。
        """
        if self._status != MonsterStatusEnum.ALIVE:
            return False
        if self._coordinate is None:
            return False
        t = self._template
        if t.starvation_ticks <= 0 or t.hunger_increase_per_tick <= 0:
            return False
        self._hunger = min(1.0, self._hunger + t.hunger_increase_per_tick)
        if self._hunger >= t.hunger_starvation_threshold:
            self._starvation_timer += 1
            return self._starvation_timer >= t.starvation_ticks
        self._starvation_timer = 0
        return False

    def record_prey_kill(self, hunger_decrease: float) -> None:
        """獲物を倒したときに飢餓を減らす。ALIVE 時のみ。飢餓無効時は何もしない。"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._template.starvation_ticks <= 0 or hunger_decrease <= 0:
            return
        self._hunger = max(0.0, min(1.0, self._hunger - hunger_decrease))

    def record_feed(self, hunger_decrease: float) -> None:
        """採食したときに飢餓を減らす。ALIVE 時のみ。飢餓無効時は何もしない。"""
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._template.starvation_ticks <= 0 or hunger_decrease <= 0:
            return
        self._hunger = max(0.0, min(1.0, self._hunger - hunger_decrease))

    def record_attacked_by(
        self,
        attacker_id: WorldObjectId,
        attacker_coordinate: Coordinate,
        current_tick: WorldTick,
    ) -> None:
        """
        外部から攻撃されたことを記録し、行動状態を更新する（被弾時のターゲット認識）。
        生態タイプ・成長段階に応じて CHASE / FLEE 等に遷移する。
        """
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
        eco = self._template.ecology_type
        if eco == EcologyTypeEnum.PATROL_ONLY:
            return
        if eco == EcologyTypeEnum.FLEE_ONLY:
            self._behavior_target_id = attacker_id
            self._behavior_last_known_position = attacker_coordinate
            self._behavior_state = BehaviorStateEnum.FLEE
            return
        if (
            eco == EcologyTypeEnum.AMBUSH
            and self._behavior_initial_position is not None
            and self._template.ambush_chase_range is not None
        ):
            if self._behavior_initial_position.distance_to(attacker_coordinate) > self._template.ambush_chase_range:
                return
        self._behavior_target_id = attacker_id
        self._behavior_last_known_position = attacker_coordinate
        hp_percentage = (
            self._hp.value / self._hp.max_hp if self._hp.max_hp > 0 else 1.0
        )
        flee_th = self.get_effective_flee_threshold(current_tick)
        allow_chase = self.get_allow_chase(current_tick)
        if hp_percentage <= flee_th:
            self._behavior_state = BehaviorStateEnum.FLEE
        elif allow_chase and self._behavior_state != BehaviorStateEnum.ENRAGE:
            self._behavior_state = BehaviorStateEnum.CHASE

    def die_from_old_age(self, current_tick: WorldTick) -> bool:
        """
        寿命で死亡させる。経過ティック（spawned_at_tick からの経過）が max_age_ticks 以上なら
        _die(cause=NATURAL) を呼ぶ。ALIVE かつ max_age_ticks が有効なときのみ判定。
        死亡した場合 True、しなかった場合 False。
        """
        if self._status != MonsterStatusEnum.ALIVE:
            return False
        if self._spawned_at_tick is None:
            return False
        max_age = self._template.max_age_ticks
        if max_age is None or max_age <= 0:
            return False
        elapsed = current_tick.value - self._spawned_at_tick.value
        if elapsed < max_age:
            return False
        self._die(current_tick, cause=DeathCauseEnum.NATURAL)
        return True

    def should_respawn(self, current_tick: WorldTick) -> bool:
        """リスポーンすべきか判定する（時間経過と is_auto_respawn のみ。SpawnCondition は呼び出し側で評価）"""
        if self._status != MonsterStatusEnum.DEAD:
            return False
        
        if not self._template.respawn_info.is_auto_respawn:
            return False

        if self._last_death_tick is None:
            return True

        elapsed = current_tick.value - self._last_death_tick.value
        return elapsed >= self._template.respawn_info.respawn_interval_ticks

    def get_respawn_coordinate(self) -> Optional[Coordinate]:
        """リスポーン時に使用する座標（初期スポーン位置）を返す。未スポーン時は None。"""
        return self._initial_spawn_coordinate

    def to_behavior_state_snapshot(
        self, actor_coordinate: Coordinate, current_tick: WorldTick
    ) -> BehaviorStateSnapshot:
        """
        状態遷移の入力用に、現在の行動状態のスナップショットを返す。
        phase_thresholds / flee_threshold はテンプレート・成長段階から取得する。
        """
        hp_percentage = (
            self._hp.value / self._hp.max_hp if self._hp.max_hp > 0 else 1.0
        )
        phase_thresholds = (
            tuple(self._template.phase_thresholds)
            if self._template.phase_thresholds
            else ()
        )
        flee_threshold = self.get_effective_flee_threshold(current_tick)
        return BehaviorStateSnapshot(
            state=self._behavior_state,
            target_id=self._behavior_target_id,
            last_known_target_position=self._behavior_last_known_position,
            hp_percentage=hp_percentage,
            phase_thresholds=phase_thresholds,
            flee_threshold=flee_threshold,
        )

    def _apply_behavior_transition(
        self, result: StateTransitionResult, current_tick: WorldTick
    ) -> None:
        """
        状態遷移結果を自身の _behavior_* に反映し、イベントを集約内で生成・add_event する。
        """
        old_state = self._behavior_state
        hp_percentage = (
            self._hp.value / self._hp.max_hp if self._hp.max_hp > 0 else 1.0
        )

        if result.apply_enrage:
            self._behavior_state = BehaviorStateEnum.ENRAGE
            self.add_event(
                ActorStateChangedEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    old_state=old_state,
                    new_state=BehaviorStateEnum.ENRAGE,
                )
            )
            old_state = BehaviorStateEnum.ENRAGE

        if result.flee_from_threat_id is not None and result.flee_from_threat_coordinate is not None:
            self._behavior_state = BehaviorStateEnum.FLEE
            self._behavior_target_id = result.flee_from_threat_id
            self._behavior_last_known_position = result.flee_from_threat_coordinate
            self.add_event(
                TargetSpottedEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    target_id=result.flee_from_threat_id,
                    coordinate=result.flee_from_threat_coordinate,
                )
            )
            if not result.apply_enrage:
                self.add_event(
                    ActorStateChangedEvent.create(
                        aggregate_id=self._world_object_id,
                        aggregate_type="Actor",
                        actor_id=self._world_object_id,
                        old_state=old_state,
                        new_state=BehaviorStateEnum.FLEE,
                    )
                )
            old_state = BehaviorStateEnum.FLEE

        if result.spot_target_params is not None:
            params = result.spot_target_params
            self._behavior_target_id = params.target_id
            self._behavior_last_known_position = params.coordinate
            effective_flee = (
                params.effective_flee_threshold
                if params.effective_flee_threshold is not None
                else self.get_effective_flee_threshold(current_tick)
            )
            allow_chase = (
                params.allow_chase if params.allow_chase is not None else True
            )
            if hp_percentage <= effective_flee:
                self._behavior_state = BehaviorStateEnum.FLEE
            elif allow_chase and self._behavior_state != BehaviorStateEnum.ENRAGE:
                self._behavior_state = BehaviorStateEnum.CHASE
            self.add_event(
                TargetSpottedEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    target_id=params.target_id,
                    coordinate=params.coordinate,
                )
            )
            if old_state != self._behavior_state:
                self.add_event(
                    ActorStateChangedEvent.create(
                        aggregate_id=self._world_object_id,
                        aggregate_type="Actor",
                        actor_id=self._world_object_id,
                        old_state=old_state,
                        new_state=self._behavior_state,
                    )
                )
            old_state = self._behavior_state

        if result.do_lose_target:
            if self._behavior_state in (
                BehaviorStateEnum.CHASE,
                BehaviorStateEnum.ENRAGE,
            ):
                self._behavior_state = BehaviorStateEnum.SEARCH
            elif self._behavior_state == BehaviorStateEnum.FLEE:
                self._behavior_state = BehaviorStateEnum.RETURN
            self._behavior_target_id = None
            self._behavior_last_known_position = None
            if result.last_known_coordinate is not None:
                self.add_event(
                    TargetLostEvent.create(
                        aggregate_id=self._world_object_id,
                        aggregate_type="Actor",
                        actor_id=self._world_object_id,
                        target_id=result.lost_target_id,
                        last_known_coordinate=result.last_known_coordinate,
                    )
                )
            if old_state != self._behavior_state:
                self.add_event(
                    ActorStateChangedEvent.create(
                        aggregate_id=self._world_object_id,
                        aggregate_type="Actor",
                        actor_id=self._world_object_id,
                        old_state=old_state,
                        new_state=self._behavior_state,
                    )
                )

    def decide(
        self,
        observation: "BehaviorObservation",
        current_tick: WorldTick,
        actor_coordinate: Coordinate,
        action_resolver: "IMonsterActionResolver",
    ) -> None:
        """
        観測と現在状態に基づき状態遷移とイベント発行を行う。
        実行すべきアクションは action_resolver で解決し、MOVE/USE_SKILL の場合は
        MonsterDecidedToMoveEvent / MonsterDecidedToUseSkillEvent を発行する。実行はハンドラが行う。
        """
        if self._status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(
                f"Monster {self._monster_id} is not alive, cannot decide"
            )
        if self._coordinate is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} is not spawned yet, cannot decide"
            )
        if self._spot_id is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} has no spot_id, cannot decide"
            )

        transition_service = BehaviorStateTransitionService()
        snapshot = self.to_behavior_state_snapshot(actor_coordinate, current_tick)
        result = transition_service.compute_transition(
            observation=observation,
            snapshot=snapshot,
            actor_id=self._world_object_id,
            actor_coordinate=actor_coordinate,
        )
        self._apply_behavior_transition(result, current_tick)

        # テリトリを超えていたら RETURN に遷移（Monster の責務）
        territory_radius = self._template.territory_radius
        if (
            territory_radius is not None
            and self._behavior_initial_position is not None
            and self._behavior_state in (
                BehaviorStateEnum.CHASE,
                BehaviorStateEnum.ENRAGE,
            )
        ):
            if (
                actor_coordinate.euclidean_distance_to(
                    self._behavior_initial_position
                )
                > float(territory_radius)
            ):
                old_state = self._behavior_state
                self._behavior_state = BehaviorStateEnum.RETURN
                self.add_event(
                    ActorStateChangedEvent.create(
                        aggregate_id=self._world_object_id,
                        aggregate_type="Actor",
                        actor_id=self._world_object_id,
                        old_state=old_state,
                        new_state=BehaviorStateEnum.RETURN,
                    )
                )

        action = action_resolver.resolve_action(
            self, observation, actor_coordinate
        )
        if action.action_type == BehaviorActionType.MOVE and action.coordinate is not None:
            self.add_event(
                MonsterDecidedToMoveEvent.create(
                    aggregate_id=self._monster_id,
                    aggregate_type="MonsterAggregate",
                    actor_id=self._world_object_id,
                    coordinate={
                        "x": action.coordinate.x,
                        "y": action.coordinate.y,
                        "z": action.coordinate.z,
                    },
                    spot_id=self._spot_id,
                    current_tick=current_tick,
                )
            )
        elif action.action_type == BehaviorActionType.USE_SKILL and action.skill_slot_index is not None:
            self.add_event(
                MonsterDecidedToUseSkillEvent.create(
                    aggregate_id=self._monster_id,
                    aggregate_type="MonsterAggregate",
                    actor_id=self._world_object_id,
                    skill_slot_index=action.skill_slot_index,
                    target_id=self._behavior_target_id,
                    spot_id=self._spot_id,
                    current_tick=current_tick,
                )
            )
        elif action.action_type == BehaviorActionType.INTERACT and action.target_id is not None:
            self.add_event(
                MonsterDecidedToInteractEvent.create(
                    aggregate_id=self._monster_id,
                    aggregate_type="MonsterAggregate",
                    actor_id=self._world_object_id,
                    target_id=action.target_id,
                    spot_id=self._spot_id,
                    current_tick=current_tick,
                )
            )
        # WAIT の場合は何も発行しない

    def respawn(self, coordinate: Coordinate, current_tick: WorldTick, spot_id: SpotId):
        """リスポーンさせる"""
        if self._status != MonsterStatusEnum.DEAD:
            raise MonsterNotDeadException(f"Monster {self._monster_id} is not dead, cannot respawn")

        if not self.should_respawn(current_tick):
            raise MonsterRespawnIntervalNotMetException(f"Monster {self._monster_id} cannot respawn yet.")

        self._spawned_at_tick = current_tick
        self._initialize_status(coordinate, spot_id, current_tick)

        self.add_event(MonsterRespawnedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": coordinate.x, "y": coordinate.y, "z": coordinate.z},
            spot_id=spot_id,
        ))

    def add_status_effect(self, effect: StatusEffect) -> None:
        """ステータス効果を追加する"""
        self._active_effects.append(effect)

    def cleanup_expired_effects(self, current_tick: WorldTick) -> None:
        """期限切れのステータス効果を削除する"""
        self._active_effects = [e for e in self._active_effects if not e.is_expired(current_tick)]

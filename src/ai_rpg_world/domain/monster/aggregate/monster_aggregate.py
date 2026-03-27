from typing import Optional, List, Tuple, TYPE_CHECKING
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
    MonsterPursuitException,
    MonsterRespawnIntervalNotMetException,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, EcologyTypeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot
from ai_rpg_world.domain.monster.value_object.feed_memory import FeedMemory, MAX_FEED_MEMORIES
from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import MonsterBehaviorState
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    StateTransitionResult,
)
from ai_rpg_world.domain.monster.service.monster_behavior_state_machine import (
    MonsterBehaviorStateMachine,
    AttackedTransitionResult,
    TransitionApplicationOutput,
    EventSpec,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    TargetSpottedEvent,
    TargetLostEvent,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import MonsterLifecycleState
from ai_rpg_world.domain.monster.value_object.monster_pursuit_state import MonsterPursuitState
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitFailedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.pack_id import PackId
    from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation


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
        behavior_state: Optional[MonsterBehaviorState] = None,
        feed_memory: Optional[FeedMemory] = None,
        pursuit_state: Optional[MonsterPursuitState] = None,
        hunger: float = 0.0,
        starvation_timer: int = 0,
    ):
        super().__init__()
        self._monster_id = monster_id
        self._template = template
        self._world_object_id = world_object_id
        self._coordinate = coordinate
        self._spot_id = spot_id
        self._active_effects = active_effects or []
        self._skill_loadout = skill_loadout
        self._pack_id = pack_id
        self._is_pack_leader = is_pack_leader
        self._initial_spawn_coordinate = initial_spawn_coordinate
        self._behavior_state = (
            behavior_state if behavior_state is not None else MonsterBehaviorState.create_idle()
        )
        self._feed_memory = feed_memory if feed_memory is not None else FeedMemory.empty()
        self._behavior_state_machine = MonsterBehaviorStateMachine()

        if status == MonsterStatusEnum.DEAD and spawned_at_tick is None:
            self._lifecycle_state = MonsterLifecycleState.create_for_unspawned(
                max_hp=template.base_stats.max_hp,
                max_mp=template.base_stats.max_mp,
            )
        else:
            _hp = hp or MonsterHp.create(template.base_stats.max_hp, template.base_stats.max_hp)
            _mp = mp or MonsterMp.create(template.base_stats.max_mp, template.base_stats.max_mp)
            _hunger = max(0.0, min(1.0, hunger))
            _starvation_timer = max(0, starvation_timer)
            self._lifecycle_state = MonsterLifecycleState(
                hp=_hp,
                mp=_mp,
                status=status,
                last_death_tick=last_death_tick,
                spawned_at_tick=spawned_at_tick,
                hunger=_hunger,
                starvation_timer=_starvation_timer,
            )
        self._pursuit_state = (
            pursuit_state if pursuit_state is not None else MonsterPursuitState()
        )

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

    @classmethod
    def reconstitute(
        cls,
        monster_id: MonsterId,
        template: MonsterTemplate,
        world_object_id: WorldObjectId,
        skill_loadout: SkillLoadoutAggregate,
        coordinate: Coordinate,
        spot_id: SpotId,
        current_tick: WorldTick,
        *,
        behavior_state: Optional[MonsterBehaviorState] = None,
        feed_memory: Optional[FeedMemory] = None,
        pursuit_state: Optional[MonsterPursuitState] = None,
        pack_id: Optional["PackId"] = None,
        is_pack_leader: bool = False,
        initial_hunger: float = 0.0,
        **kwargs,
    ) -> "MonsterAggregate":
        """
        スポーン済みの状態でモンスターを再構成する（永続化層・テスト用）。
        create() + spawn() と同等の初期状態を構築し、任意で behavior_state / feed_memory / pursuit_state を指定可能。
        """
        base = template.base_stats
        lifecycle = MonsterLifecycleState.create_for_spawned(
            max_hp=base.max_hp,
            max_mp=base.max_mp,
            spawned_at_tick=current_tick,
            initial_hunger=initial_hunger,
        )
        return cls(
            monster_id=monster_id,
            template=template,
            world_object_id=world_object_id,
            skill_loadout=skill_loadout,
            hp=lifecycle.hp,
            mp=lifecycle.mp,
            status=MonsterStatusEnum.ALIVE,
            coordinate=coordinate,
            spot_id=spot_id,
            pack_id=pack_id,
            is_pack_leader=is_pack_leader,
            initial_spawn_coordinate=coordinate,
            spawned_at_tick=current_tick,
            behavior_state=behavior_state or MonsterBehaviorState.create_idle(coordinate),
            feed_memory=feed_memory or FeedMemory.empty(),
            pursuit_state=pursuit_state or MonsterPursuitState(),
            hunger=initial_hunger,
            **kwargs,
        )

    @property
    def monster_id(self) -> MonsterId:
        return self._monster_id

    @property
    def template(self) -> MonsterTemplate:
        return self._template

    def _get_current_growth_stage(
        self, current_tick: WorldTick, effective_spawned_at_tick: Optional[WorldTick] = None
    ) -> Optional[GrowthStage]:
        """現在の成長段階を返す。未スポーンまたは段階なしの場合は None。effective_spawned_at_tick は初期化時などに使用。"""
        spawned = effective_spawned_at_tick or self._lifecycle_state.spawned_at_tick
        if spawned is None:
            return None
        stages = self._template.growth_stages
        if not stages:
            return None
        elapsed = current_tick.value - spawned.value
        if elapsed < 0:
            return None
        stage = None
        for g in stages:
            if elapsed >= g.after_ticks:
                stage = g
        return stage

    def get_current_growth_multiplier(
        self, current_tick: WorldTick, effective_spawned_at_tick: Optional[WorldTick] = None
    ) -> float:
        """
        現在の成長段階に応じたステータス乗率を返す。
        spawned_at_tick が未設定または growth_stages が空の場合は 1.0。
        """
        stage = self._get_current_growth_stage(current_tick, effective_spawned_at_tick)
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

    def get_base_stats_with_growth(
        self, current_tick: WorldTick, effective_spawned_at_tick: Optional[WorldTick] = None
    ) -> BaseStats:
        """成長段階のみ適用した BaseStats（バフ・デバフは含まない）。実効ステータスはアプリ層で compute_effective_stats を使用すること。"""
        base = self._template.base_stats
        growth_mult = self.get_current_growth_multiplier(current_tick, effective_spawned_at_tick)
        return BaseStats(
            max_hp=max(1, int(base.max_hp * growth_mult)),
            max_mp=max(1, int(base.max_mp * growth_mult)),
            attack=int(base.attack * growth_mult),
            defense=int(base.defense * growth_mult),
            speed=int(base.speed * growth_mult),
            critical_rate=base.critical_rate,
            evasion_rate=base.evasion_rate,
        )

    @property
    def active_effects(self) -> List[StatusEffect]:
        """適用中のステータス効果（変更不可のコピー）。実効ステータスはアプリ層で compute_effective_stats を使用すること。"""
        return list(self._active_effects)

    @property
    def world_object_id(self) -> WorldObjectId:
        return self._world_object_id

    @property
    def hp(self) -> MonsterHp:
        return self._lifecycle_state.hp

    @property
    def mp(self) -> MonsterMp:
        return self._lifecycle_state.mp

    @property
    def status(self) -> MonsterStatusEnum:
        return self._lifecycle_state.status

    @property
    def last_death_tick(self) -> Optional[WorldTick]:
        return self._lifecycle_state.last_death_tick

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
        return self._lifecycle_state.spawned_at_tick

    @property
    def behavior_state(self) -> BehaviorStateEnum:
        return self._behavior_state.state

    @property
    def behavior_target_id(self) -> Optional[WorldObjectId]:
        return self._behavior_state.target_id

    @property
    def behavior_last_known_position(self) -> Optional[Coordinate]:
        return self._behavior_state.last_known_position

    @property
    def behavior_initial_position(self) -> Optional[Coordinate]:
        return self._behavior_state.initial_position

    @property
    def behavior_patrol_index(self) -> int:
        return self._behavior_state.patrol_index

    @property
    def behavior_search_timer(self) -> int:
        return self._behavior_state.search_timer

    @property
    def behavior_failure_count(self) -> int:
        return self._behavior_state.failure_count

    @property
    def pursuit_state(self) -> Optional[PursuitState]:
        if isinstance(self._pursuit_state, MonsterPursuitState):
            return self._pursuit_state.pursuit
        return self._pursuit_state

    @property
    def has_active_pursuit(self) -> bool:
        if isinstance(self._pursuit_state, MonsterPursuitState):
            return self._pursuit_state.has_active_pursuit
        return self._pursuit_state is not None

    @property
    def pursuit_target_id(self) -> Optional[WorldObjectId]:
        return self._pursuit_state.target_id

    @property
    def pursuit_target_snapshot(self) -> Optional[PursuitTargetSnapshot]:
        return self._pursuit_state.target_snapshot

    @property
    def pursuit_last_known(self) -> Optional[PursuitLastKnownState]:
        return self._pursuit_state.last_known

    @property
    def behavior_last_known_feed(self) -> List[FeedMemoryEntry]:
        """餌場の記憶（最大 MAX_FEED_MEMORIES 件、古い順）。適用時は距離が近い順に使う。"""
        return list(self._feed_memory.entries)

    def remember_feed(self, object_id: WorldObjectId, coordinate: Coordinate) -> None:
        """
        餌オブジェクトの位置を記憶する。最大 MAX_FEED_MEMORIES 件を LRU で保持し、
        超えた分は古いものから追い出す。既に同じ object_id がある場合は更新（末尾に移動）。
        """
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            return
        self._feed_memory = self._feed_memory.remember(object_id, coordinate)

    def advance_patrol_index(self, patrol_points_count: int) -> None:
        """パトロール点に到達したときにインデックスを進める。patrol_points_count は点の数。"""
        self._behavior_state = self._behavior_state.advance_patrol_index(patrol_points_count)

    def _initialize_status(
        self,
        coordinate: Coordinate,
        spot_id: SpotId,
        current_tick: WorldTick,
        initial_hunger: float = 0.0,
    ) -> None:
        """
        ステータスを初期化（出現/リスポーン時）。
        呼び出し元で spawned_at_tick を current_tick に設定したうえで呼ぶこと。
        HP/MP は実効ステータスで満タンに初期化。行動状態・飢餓もリセット（initial_hunger で指定可能）。
        """
        self._coordinate = coordinate
        self._spot_id = spot_id
        base_with_growth = self.get_base_stats_with_growth(
            current_tick, effective_spawned_at_tick=current_tick
        )
        self._lifecycle_state = self._lifecycle_state.with_spawn_reset(
            max_hp=base_with_growth.max_hp,
            max_mp=base_with_growth.max_mp,
            spawned_at_tick=current_tick,
            initial_hunger=initial_hunger,
        )
        self._behavior_state = self._behavior_state.with_spawn_reset(coordinate)
        self._feed_memory = self._feed_memory.cleared()
        self._pursuit_state = self._pursuit_state.cleared()

    @property
    def hunger(self) -> float:
        """現在の飢餓値（0.0〜1.0）。"""
        return self._lifecycle_state.hunger

    def update_map_placement(self, spot_id: SpotId, coordinate: Coordinate) -> None:
        """ゲートウェイ等によるマップ間移動時に座標・スポットを更新する（ALIVE時のみ想定）"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
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
        if self._coordinate is not None or self._lifecycle_state.status == MonsterStatusEnum.ALIVE:
            raise MonsterAlreadySpawnedException(f"Monster {self._monster_id} is already spawned at {self._coordinate}")

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
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            if self._lifecycle_state.status == MonsterStatusEnum.DEAD and self._lifecycle_state.last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")

        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        self._lifecycle_state = self._lifecycle_state.apply_damage(final_damage)
        
        self.add_event(MonsterDamagedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            damage=final_damage,
            current_hp=self._lifecycle_state.hp.value,
            attacker_id=attacker_id
        ))

        if not self._lifecycle_state.hp.is_alive():
            cause = DeathCauseEnum.KILLED_BY_PLAYER if killer_player_id else DeathCauseEnum.KILLED_BY_MONSTER
            self._die(
                current_tick,
                killer_player_id=killer_player_id,
                killer_world_object_id=attacker_id,
                cause=cause if (killer_player_id or attacker_id) else None,
            )

    def record_evasion(self):
        """回避を記録する（ALIVE時のみ）"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            if self._lifecycle_state.status == MonsterStatusEnum.DEAD and self._lifecycle_state.last_death_tick is None:
                raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")

        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        self.add_event(MonsterEvadedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            coordinate={"x": self._coordinate.x, "y": self._coordinate.y, "z": self._coordinate.z},
            current_hp=self._lifecycle_state.hp.value,
        ))

    def heal_hp(self, amount: int):
        """HPを回復する"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        old_hp = self._lifecycle_state.hp.value
        self._lifecycle_state = self._lifecycle_state.apply_heal(amount)
        actual_healed = self._lifecycle_state.hp.value - old_hp

        if actual_healed > 0:
            self.add_event(MonsterHealedEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                amount=actual_healed,
                current_hp=self._lifecycle_state.hp.value
            ))

    def recover_mp(self, amount: int):
        """MPを回復する"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        old_mp = self._lifecycle_state.mp.value
        self._lifecycle_state = self._lifecycle_state.apply_mp_recovery(amount)
        actual_recovered = self._lifecycle_state.mp.value - old_mp

        if actual_recovered > 0:
            self.add_event(MonsterMpRecoveredEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                amount=actual_recovered,
                current_mp=self._lifecycle_state.mp.value
            ))

    def use_mp(self, amount: int):
        """MPを消費する"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        
        # MonsterMp.use 内で MonsterInsufficientMpException が投げられる
        self._lifecycle_state = self._lifecycle_state.apply_mp_use(amount)

    def on_tick(
        self,
        current_tick: WorldTick,
        regen_stats: Optional[BaseStats] = None,
        regen_rate: Optional[float] = None,
    ) -> None:
        """時間経過による処理（自然回復など）。

        regen_stats はアプリ層で compute_effective_stats により算出して渡す。
        regen_rate はアプリ層で MonsterConfigService 等から取得して渡す。集約は値のみで計算する。
        """
        if (
            self._lifecycle_state.status == MonsterStatusEnum.ALIVE
            and regen_stats is not None
            and regen_rate is not None
        ):
            hp_regen = max(1, int(regen_stats.max_hp * regen_rate))
            mp_regen = max(1, int(regen_stats.max_mp * regen_rate))
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
        """
        死亡する（内部用）。
        cause が None になるのは、killer_player_id も attacker_id もない場合
        （例: 環境ダメージ等で原因が特定できないケース）。
        """
        if self._lifecycle_state.status == MonsterStatusEnum.DEAD:
            return

        self._lifecycle_state = self._lifecycle_state.with_death(current_tick)
        spot_id_for_event = self._spot_id
        self._behavior_state = self._behavior_state.with_target_cleared()
        self._clear_pursuit_state()
        self._coordinate = None  # 死亡時は座標をクリア（spot_id はリスポーン判定のため保持）

        respawn_tick = current_tick.value + self._template.respawn_info.respawn_interval_ticks

        self.add_event(MonsterDiedEvent.create(
            aggregate_id=self._monster_id,
            aggregate_type="MonsterAggregate",
            respawn_tick=respawn_tick,
            exp=self._template.reward_info.exp,
            gold=self._template.reward_info.gold,
            template_id=self._template.template_id.value,
            loot_table_id=self._template.reward_info.loot_table_id,
            killer_player_id=killer_player_id,
            killer_world_object_id=killer_world_object_id,
            cause=cause,
            spot_id=spot_id_for_event,
        ))

    def starve(self, current_tick: WorldTick) -> None:
        """飢餓で死亡させる。ALIVE のときのみ有効。"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            if self._lifecycle_state.status == MonsterStatusEnum.DEAD and self._lifecycle_state.last_death_tick is None:
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
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            return False
        if self._coordinate is None:
            return False
        t = self._template
        if t.starvation_ticks <= 0 or t.hunger_increase_per_tick <= 0:
            return False
        new_lifecycle, should_starve = self._lifecycle_state.tick_hunger(
            hunger_increase_per_tick=t.hunger_increase_per_tick,
            hunger_starvation_threshold=t.hunger_starvation_threshold,
            starvation_ticks=t.starvation_ticks,
        )
        self._lifecycle_state = new_lifecycle
        return should_starve

    def record_prey_kill(self, hunger_decrease: float) -> None:
        """獲物を倒したときに飢餓を減らす。ALIVE 時のみ。飢餓無効時は何もしない。"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._template.starvation_ticks <= 0 or hunger_decrease <= 0:
            return
        self._lifecycle_state = self._lifecycle_state.decrease_hunger(hunger_decrease)

    def record_feed(self, hunger_decrease: float) -> None:
        """採食したときに飢餓を減らす。ALIVE 時のみ。飢餓無効時は何もしない。"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._template.starvation_ticks <= 0 or hunger_decrease <= 0:
            return
        self._lifecycle_state = self._lifecycle_state.decrease_hunger(hunger_decrease)

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
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(f"Monster {self._monster_id} is not alive")
        if self._coordinate is None:
            raise MonsterNotSpawnedException(f"Monster {self._monster_id} is not spawned yet")

        transition = self._behavior_state_machine.compute_attacked_transition(
            attacker_id=attacker_id,
            attacker_coordinate=attacker_coordinate,
            ecology_type=self._template.ecology_type,
            hp_percentage=(
                self._lifecycle_state.hp.value / self._lifecycle_state.hp.max_hp if self._lifecycle_state.hp.max_hp > 0 else 1.0
            ),
            effective_flee_threshold=self.get_effective_flee_threshold(current_tick),
            allow_chase=self.get_allow_chase(current_tick),
            current_behavior_state=self._behavior_state.state,
            behavior_initial_position=self._behavior_state.initial_position,
            ambush_chase_range=self._template.ambush_chase_range,
        )
        if transition.no_transition:
            return
        self._behavior_state = self._behavior_state.with_attacked(transition)
        if transition.clear_pursuit:
            self._clear_pursuit_state()
        elif transition.sync_pursuit:
            self._sync_active_pursuit_state(
                target_id=attacker_id,
                coordinate=attacker_coordinate,
                observed_at_tick=current_tick,
            )

    def die_from_old_age(self, current_tick: WorldTick) -> bool:
        """
        寿命で死亡させる。経過ティック（spawned_at_tick からの経過）が max_age_ticks 以上なら
        _die(cause=NATURAL) を呼ぶ。ALIVE かつ max_age_ticks が有効なときのみ判定。
        死亡した場合 True、しなかった場合 False。
        """
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            return False
        if self._lifecycle_state.spawned_at_tick is None:
            return False
        max_age = self._template.max_age_ticks
        if max_age is None or max_age <= 0:
            return False
        elapsed = current_tick.value - self._lifecycle_state.spawned_at_tick.value
        if elapsed < max_age:
            return False
        self._die(current_tick, cause=DeathCauseEnum.NATURAL)
        return True

    def should_respawn(self, current_tick: WorldTick) -> bool:
        """リスポーンすべきか判定する（時間経過と is_auto_respawn のみ。SpawnCondition は呼び出し側で評価）"""
        if self._lifecycle_state.status != MonsterStatusEnum.DEAD:
            return False
        
        if not self._template.respawn_info.is_auto_respawn:
            return False

        if self._lifecycle_state.last_death_tick is None:
            return True

        elapsed = current_tick.value - self._lifecycle_state.last_death_tick.value
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
            self._lifecycle_state.hp.value / self._lifecycle_state.hp.max_hp if self._lifecycle_state.hp.max_hp > 0 else 1.0
        )
        phase_thresholds = (
            tuple(self._template.phase_thresholds)
            if self._template.phase_thresholds
            else ()
        )
        flee_threshold = self.get_effective_flee_threshold(current_tick)
        return BehaviorStateSnapshot(
            state=self._behavior_state.state,
            target_id=self._behavior_state.target_id,
            last_known_target_position=self._behavior_state.last_known_position,
            hp_percentage=hp_percentage,
            phase_thresholds=phase_thresholds,
            flee_threshold=flee_threshold,
        )

    def _ensure_can_perform_behavior(self) -> None:
        """状態遷移・アクション記録の前提条件（ALIVE・スポーン済み・spot_id あり）を検証する。"""
        if self._lifecycle_state.status != MonsterStatusEnum.ALIVE:
            raise MonsterAlreadyDeadException(
                f"Monster {self._monster_id} is not alive, cannot perform behavior"
            )
        if self._coordinate is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} is not spawned yet, cannot perform behavior"
            )
        if self._spot_id is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} has no spot_id, cannot perform behavior"
            )

    def _build_pursuit_target_snapshot(
        self, target_id: WorldObjectId, coordinate: Coordinate
    ) -> PursuitTargetSnapshot:
        if self._spot_id is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} has no spot_id, cannot build pursuit snapshot"
            )
        return PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=self._spot_id,
            coordinate=coordinate,
        )

    def _build_pursuit_last_known(
        self,
        target_id: WorldObjectId,
        coordinate: Coordinate,
        observed_at_tick: Optional[WorldTick],
    ) -> PursuitLastKnownState:
        if self._spot_id is None:
            raise MonsterNotSpawnedException(
                f"Monster {self._monster_id} has no spot_id, cannot build pursuit last-known state"
            )
        return PursuitLastKnownState(
            target_id=target_id,
            spot_id=self._spot_id,
            coordinate=coordinate,
            observed_at_tick=observed_at_tick,
        )

    def _sync_active_pursuit_state(
        self,
        target_id: WorldObjectId,
        coordinate: Coordinate,
        observed_at_tick: Optional[WorldTick],
    ) -> None:
        current = self._pursuit_state
        if isinstance(current, PursuitState):
            current = MonsterPursuitState(pursuit=current)
        snapshot = self._build_pursuit_target_snapshot(target_id, coordinate)
        last_known = self._build_pursuit_last_known(
            target_id=target_id,
            coordinate=coordinate,
            observed_at_tick=observed_at_tick,
        )
        self._pursuit_state = current.with_sync(
            actor_id=self._world_object_id,
            target_id=target_id,
            target_snapshot=snapshot,
            last_known=last_known,
        )

    def _preserve_pursuit_last_known(
        self,
        target_id: WorldObjectId,
        coordinate: Coordinate,
        observed_at_tick: Optional[WorldTick],
    ) -> None:
        current = self._pursuit_state
        if isinstance(current, PursuitState):
            current = MonsterPursuitState(pursuit=current)
        fallback_snapshot = self._build_pursuit_target_snapshot(target_id, coordinate)
        last_known = self._build_pursuit_last_known(
            target_id=target_id,
            coordinate=coordinate,
            observed_at_tick=observed_at_tick,
        )
        self._pursuit_state = current.with_preserve_last_known(
            actor_id=self._world_object_id,
            target_id=target_id,
            last_known=last_known,
            target_snapshot=fallback_snapshot,
        )

    def _clear_pursuit_state(self) -> None:
        if isinstance(self._pursuit_state, MonsterPursuitState):
            self._pursuit_state = self._pursuit_state.cleared()
        else:
            self._pursuit_state = MonsterPursuitState()

    def _emit_behavior_event(self, ev_spec: "EventSpec") -> None:
        """EventSpec に従ってイベントを発行する。"""
        if ev_spec.kind == "target_spotted":
            self.add_event(
                TargetSpottedEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    target_id=ev_spec.target_id,
                    coordinate=ev_spec.coordinate,
                )
            )
        elif ev_spec.kind == "target_lost":
            self.add_event(
                TargetLostEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    target_id=ev_spec.target_id,
                    last_known_coordinate=ev_spec.last_known_coordinate,
                )
            )
        elif ev_spec.kind == "actor_state_changed":
            self.add_event(
                ActorStateChangedEvent.create(
                    aggregate_id=self._world_object_id,
                    aggregate_type="Actor",
                    actor_id=self._world_object_id,
                    old_state=ev_spec.old_state,
                    new_state=ev_spec.new_state,
                )
            )

    def fail_pursuit(
        self,
        reason: PursuitFailureReason,
        *,
        current_tick: Optional[WorldTick] = None,
    ) -> None:
        """共有 pursuit 語彙でモンスター追跡を失敗終了する。"""
        if not self.has_active_pursuit:
            raise MonsterPursuitException(
                "Cannot fail pursuit when no active pursuit exists."
            )

        current_state = self._pursuit_state
        last_known = current_state.last_known
        target_snapshot = current_state.target_snapshot
        if last_known is None:
            coordinate = self._behavior_state.last_known_position
            if coordinate is None:
                raise MonsterPursuitException(
                    "Cannot fail pursuit without last-known state."
                )
            last_known = self._build_pursuit_last_known(
                target_id=current_state.target_id,
                coordinate=coordinate,
                observed_at_tick=current_tick,
            )

        self.add_event(
            PursuitFailedEvent.create(
                aggregate_id=self._world_object_id,
                aggregate_type="MonsterAggregate",
                actor_id=self._world_object_id,
                target_id=current_state.target_id,
                failure_reason=reason,
                last_known=last_known,
                target_snapshot=target_snapshot,
            )
        )
        self._behavior_state = self._behavior_state.with_target_cleared()
        self._clear_pursuit_state()

    def apply_behavior_transition(
        self, result: StateTransitionResult, current_tick: WorldTick
    ) -> None:
        """
        状態遷移結果を自身の _behavior_* に反映し、イベントを集約内で生成・add_event する。
        アプリ層で BehaviorStateTransitionService.compute_transition の結果を渡す。
        """
        self._ensure_can_perform_behavior()
        hp_percentage = (
            self._lifecycle_state.hp.value / self._lifecycle_state.hp.max_hp if self._lifecycle_state.hp.max_hp > 0 else 1.0
        )
        output = self._behavior_state_machine.apply_transition(
            result=result,
            current_state=self._behavior_state.state,
            current_target_id=self._behavior_state.target_id,
            current_last_known_position=self._behavior_state.last_known_position,
            hp_percentage=hp_percentage,
            effective_flee_threshold=self.get_effective_flee_threshold(current_tick),
            allow_chase=self.get_allow_chase(current_tick),
        )
        self._behavior_state = self._behavior_state.with_transition(output)
        if output.clear_pursuit:
            self._clear_pursuit_state()
        if output.sync_pursuit is not None:
            tid, coord = output.sync_pursuit
            self._sync_active_pursuit_state(
                target_id=tid,
                coordinate=coord,
                observed_at_tick=current_tick,
            )
        if output.preserve_pursuit_last_known is not None:
            tid, coord = output.preserve_pursuit_last_known
            self._preserve_pursuit_last_known(
                target_id=tid,
                coordinate=coord,
                observed_at_tick=current_tick,
            )
        for ev_spec in output.events:
            self._emit_behavior_event(ev_spec)

    def apply_territory_return_if_needed(self, actor_coordinate: Coordinate) -> None:
        """
        テリトリを超えていたら RETURN に遷移する（Monster の責務）。
        アプリ層で apply_behavior_transition の後に呼ぶ。
        """
        self._ensure_can_perform_behavior()
        if not self._behavior_state_machine.should_return_to_territory(
            actor_coordinate=actor_coordinate,
            behavior_initial_position=self._behavior_state.initial_position,
            territory_radius=self._template.territory_radius,
            current_state=self._behavior_state.state,
        ):
            return
        old_state = self._behavior_state.state
        self._behavior_state = self._behavior_state.with_territory_return()
        self._clear_pursuit_state()
        self.add_event(
            ActorStateChangedEvent.create(
                aggregate_id=self._world_object_id,
                aggregate_type="Actor",
                actor_id=self._world_object_id,
                old_state=old_state,
                new_state=BehaviorStateEnum.RETURN,
            )
        )

    def record_move(
        self, coordinate: Coordinate, current_tick: WorldTick
    ) -> None:
        """決まった移動先を記録し MonsterDecidedToMoveEvent を発行する。アプリ層で resolve_action の結果に応じて呼ぶ。"""
        self._ensure_can_perform_behavior()
        self.add_event(
            MonsterDecidedToMoveEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                actor_id=self._world_object_id,
                coordinate={
                    "x": coordinate.x,
                    "y": coordinate.y,
                    "z": coordinate.z,
                },
                spot_id=self._spot_id,
                current_tick=current_tick,
            )
        )

    def record_use_skill(
        self,
        skill_slot_index: int,
        target_id: Optional[WorldObjectId],
        current_tick: WorldTick,
    ) -> None:
        """決まったスキル使用を記録し MonsterDecidedToUseSkillEvent を発行する。アプリ層で resolve_action の結果に応じて呼ぶ。"""
        self._ensure_can_perform_behavior()
        self.add_event(
            MonsterDecidedToUseSkillEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                actor_id=self._world_object_id,
                skill_slot_index=skill_slot_index,
                target_id=target_id,
                spot_id=self._spot_id,
                current_tick=current_tick,
            )
        )

    def record_interact(
        self, target_id: WorldObjectId, current_tick: WorldTick
    ) -> None:
        """決まったインタラクト対象を記録し MonsterDecidedToInteractEvent を発行する。アプリ層で resolve_action の結果に応じて呼ぶ。"""
        self._ensure_can_perform_behavior()
        self.add_event(
            MonsterDecidedToInteractEvent.create(
                aggregate_id=self._monster_id,
                aggregate_type="MonsterAggregate",
                actor_id=self._world_object_id,
                target_id=target_id,
                spot_id=self._spot_id,
                current_tick=current_tick,
            )
        )

    def respawn(self, coordinate: Coordinate, current_tick: WorldTick, spot_id: SpotId):
        """リスポーンさせる"""
        if self._lifecycle_state.status != MonsterStatusEnum.DEAD:
            raise MonsterNotDeadException(f"Monster {self._monster_id} is not dead, cannot respawn")

        if not self.should_respawn(current_tick):
            raise MonsterRespawnIntervalNotMetException(f"Monster {self._monster_id} cannot respawn yet.")

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

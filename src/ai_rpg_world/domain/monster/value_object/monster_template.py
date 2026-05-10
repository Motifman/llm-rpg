from dataclasses import dataclass
from typing import List, Optional, Set, TYPE_CHECKING
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
if TYPE_CHECKING:
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage, MAX_GROWTH_STAGES
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.monster.enum.monster_enum import (
    ActiveTimeType,
    EcologyTypeEnum,
    ReactionPolicyEnum,
)


@dataclass(frozen=True)
class MonsterTemplate:
    """モンスターの種族・定義情報"""
    template_id: MonsterTemplateId
    name: str
    base_stats: BaseStats
    reward_info: RewardInfo
    respawn_info: RespawnInfo
    race: Race
    faction: MonsterFactionEnum
    description: str
    skill_ids: List[SkillId] = None
    vision_range: int = 5
    flee_threshold: float = 0.2
    behavior_strategy_type: str = "default"
    phase_thresholds: Optional[List[float]] = None
    ecology_type: EcologyTypeEnum = EcologyTypeEnum.NORMAL
    ambush_chase_range: Optional[int] = None
    territory_radius: Optional[int] = None
    active_time: ActiveTimeType = ActiveTimeType.ALWAYS
    # `Race` enum セット: typo を template 構築時に弾き、IDE 補完を効かせる。
    # SQLite 永続化では `Race.value` 文字列で保存し、読出時に `Race(...)` で
    # enum に戻す（codec 側で吸収）。
    threat_races: Optional[Set[Race]] = None
    prey_races: Optional[Set[Race]] = None
    growth_stages: Optional[List[GrowthStage]] = None
    # Phase 6: 飢餓（None/0 で無効）
    hunger_increase_per_tick: float = 0.0
    hunger_decrease_on_prey_kill: float = 0.0
    hunger_starvation_threshold: float = 1.0
    starvation_ticks: int = 0
    # 寿命（Optional[int]、None/0 で無効。経過ティック ≥ max_age_ticks で NATURAL 死亡）
    max_age_ticks: Optional[int] = None
    # 採食: この値以上で餌探し優先。1回の採食で減らす飢餓量。餌とみなす LootTable の item_spec_id 集合
    forage_threshold: float = 1.0
    hunger_decrease_on_feed: float = 0.0
    preferred_feed_item_spec_ids: Optional[Set["ItemSpecId"]] = None
    # スポットグラフ戦闘用パラメータ。
    # - `has_dark_vision`: True なら暗闇でもプレイヤーを視認できる。
    # - `attack_cooldown_ticks`: 1 回攻撃した後、次の攻撃まで待つ tick 数。
    #   1 にすると毎 tick 攻撃可能。0 以下は不正。
    has_dark_vision: bool = False
    attack_cooldown_ticks: int = 1
    # スポットグラフ徘徊の確率 (0.0 〜 1.0)。tick service が「攻撃しない時」
    # にこの確率で隣接スポットへランダム移動を試みる。0.0 で完全静止、1.0 で
    # 毎 tick 必ず移動を試みる。`ecology_type=AMBUSH` なら本値によらず
    # 移動しない。
    # **デフォルトは 0.0 (静止)**。ボスや陳列目的の NPC モンスターが意図せず
    # 動かないよう、徘徊させたいテンプレだけシナリオ側で明示する opt-in 方針。
    idle_wander_chance: float = 0.0
    # Phase 4a: 攻撃を受けたときの反応 policy。詳細は `ReactionPolicyEnum`。
    # デフォルトは PASSIVE で既存挙動と同じ（反応しない）。
    reaction_to_attack: ReactionPolicyEnum = ReactionPolicyEnum.PASSIVE
    # 攻撃を受けてから何 tick 反応 (FLEE / CHASE) を続けるか。0 で即時忘却 →
    # 反応しない。3-5 程度が自然な動物行動の目安。
    flee_grace_ticks: int = 3
    # Phase 4b PR (b): CHASE 中に target を見失った場合、`last_observed_target_spot_id`
    # に到着した後にそのスポット周辺を探索する tick 数。0 なら探索フェーズなし
    # (見失い即 IDLE 復帰)。3-5 程度で「諦め悪い敵」を表現。
    #
    # 挙動:
    # - 0: 探索フェーズなし。last_observed 到着 tick で即 IDLE。
    # - 1: 到着 tick で wander 1 回実行 → 即 IDLE (1 tick 分の wander で消費)。
    # - N (>=2): 到着 tick + 後続 (N-1) tick で計 N 回 wander → IDLE。
    chase_search_ticks: int = 3

    def __post_init__(self):
        object.__setattr__(self, "skill_ids", self.skill_ids or [])
        object.__setattr__(self, "phase_thresholds", self.phase_thresholds or [])
        object.__setattr__(self, "threat_races", self.threat_races or frozenset())
        object.__setattr__(self, "prey_races", self.prey_races or frozenset())
        object.__setattr__(self, "growth_stages", self.growth_stages or [])
        object.__setattr__(self, "preferred_feed_item_spec_ids", self.preferred_feed_item_spec_ids or frozenset())
        if not isinstance(self.skill_ids, list):
            raise MonsterTemplateValidationException(
                f"skill_ids must be a list, got {type(self.skill_ids).__name__}"
            )
        for i, e in enumerate(self.skill_ids):
            if not isinstance(e, SkillId):
                raise MonsterTemplateValidationException(
                    f"skill_ids[{i}] must be SkillId, got {type(e).__name__}"
                )
        if not self.name or not self.name.strip():
            raise MonsterTemplateValidationException("Monster name cannot be empty")
        
        if not self.description or not self.description.strip():
            raise MonsterTemplateValidationException("Monster description cannot be empty")
        
        if len(self.description) > 1000:
            raise MonsterTemplateValidationException("Monster description is too long (max 1000 characters)")
        
        if not isinstance(self.race, Race):
            raise MonsterTemplateValidationException(f"Invalid race: {self.race}")
            
        if not isinstance(self.faction, MonsterFactionEnum):
            raise MonsterTemplateValidationException(f"Invalid faction: {self.faction}")

        if not isinstance(self.has_dark_vision, bool):
            raise MonsterTemplateValidationException(
                f"has_dark_vision must be bool, got {type(self.has_dark_vision).__name__}"
            )
        if not isinstance(self.attack_cooldown_ticks, int) or isinstance(
            self.attack_cooldown_ticks, bool
        ):
            raise MonsterTemplateValidationException(
                "attack_cooldown_ticks must be int"
            )
        if self.attack_cooldown_ticks < 1:
            raise MonsterTemplateValidationException(
                f"attack_cooldown_ticks must be >= 1, got {self.attack_cooldown_ticks}"
            )
        if not isinstance(self.idle_wander_chance, (int, float)) or isinstance(
            self.idle_wander_chance, bool
        ):
            raise MonsterTemplateValidationException(
                "idle_wander_chance must be float"
            )
        if not (0.0 <= self.idle_wander_chance <= 1.0):
            raise MonsterTemplateValidationException(
                f"idle_wander_chance must be between 0.0 and 1.0, "
                f"got {self.idle_wander_chance}"
            )
        if not isinstance(self.reaction_to_attack, ReactionPolicyEnum):
            raise MonsterTemplateValidationException(
                f"reaction_to_attack must be ReactionPolicyEnum, "
                f"got {type(self.reaction_to_attack).__name__}"
            )
        if not isinstance(self.flee_grace_ticks, int) or isinstance(
            self.flee_grace_ticks, bool
        ):
            raise MonsterTemplateValidationException(
                "flee_grace_ticks must be int"
            )
        if self.flee_grace_ticks < 0:
            raise MonsterTemplateValidationException(
                f"flee_grace_ticks must be >= 0, got {self.flee_grace_ticks}"
            )
        if not isinstance(self.chase_search_ticks, int) or isinstance(
            self.chase_search_ticks, bool
        ):
            raise MonsterTemplateValidationException(
                "chase_search_ticks must be int"
            )
        if self.chase_search_ticks < 0:
            raise MonsterTemplateValidationException(
                f"chase_search_ticks must be >= 0, got {self.chase_search_ticks}"
            )

        if self.vision_range < 0:
            raise MonsterTemplateValidationException(
                f"vision_range cannot be negative: {self.vision_range}"
            )
        if not (0.0 <= self.flee_threshold <= 1.0):
            raise MonsterTemplateValidationException(
                f"flee_threshold must be between 0.0 and 1.0: {self.flee_threshold}"
            )
        for i, t in enumerate(self.phase_thresholds):
            if not (0.0 <= t <= 1.0):
                raise MonsterTemplateValidationException(
                    f"phase_thresholds[{i}] must be between 0.0 and 1.0: {t}"
                )
        if self.ambush_chase_range is not None and self.ambush_chase_range < 0:
            raise MonsterTemplateValidationException(
                f"ambush_chase_range cannot be negative: {self.ambush_chase_range}"
            )
        if self.territory_radius is not None and self.territory_radius < 0:
            raise MonsterTemplateValidationException(
                f"territory_radius cannot be negative: {self.territory_radius}"
            )
        if not isinstance(self.ecology_type, EcologyTypeEnum):
            raise MonsterTemplateValidationException(
                f"ecology_type must be EcologyTypeEnum, got {type(self.ecology_type).__name__}"
            )
        if not isinstance(self.active_time, ActiveTimeType):
            raise MonsterTemplateValidationException(
                f"active_time must be ActiveTimeType, got {type(self.active_time).__name__}"
            )
        if self.threat_races is not None and not isinstance(self.threat_races, (set, frozenset)):
            raise MonsterTemplateValidationException(
                f"threat_races must be a set or frozenset, got {type(self.threat_races).__name__}"
            )
        for r in self.threat_races or ():
            if not isinstance(r, Race):
                raise MonsterTemplateValidationException(
                    f"threat_races must contain Race enum values, got {type(r).__name__}"
                )
        if self.prey_races is not None and not isinstance(self.prey_races, (set, frozenset)):
            raise MonsterTemplateValidationException(
                f"prey_races must be a set or frozenset, got {type(self.prey_races).__name__}"
            )
        for r in self.prey_races or ():
            if not isinstance(r, Race):
                raise MonsterTemplateValidationException(
                    f"prey_races must contain Race enum values, got {type(r).__name__}"
                )
        if self.growth_stages is not None:
            if not isinstance(self.growth_stages, list):
                raise MonsterTemplateValidationException(
                    f"growth_stages must be a list, got {type(self.growth_stages).__name__}"
                )
            if len(self.growth_stages) > MAX_GROWTH_STAGES:
                raise MonsterTemplateValidationException(
                    f"growth_stages must have at most {MAX_GROWTH_STAGES} stages, got {len(self.growth_stages)}"
                )
            for i, g in enumerate(self.growth_stages):
                if not isinstance(g, GrowthStage):
                    raise MonsterTemplateValidationException(
                        f"growth_stages[{i}] must be GrowthStage, got {type(g).__name__}"
                    )
            if self.growth_stages:
                sorted_ticks = [g.after_ticks for g in sorted(self.growth_stages, key=lambda x: x.after_ticks)]
                if sorted_ticks != [g.after_ticks for g in self.growth_stages]:
                    raise MonsterTemplateValidationException(
                        "growth_stages must be ordered by after_ticks ascending"
                    )
                if self.growth_stages[0].after_ticks != 0:
                    raise MonsterTemplateValidationException(
                        "first growth_stage must have after_ticks=0"
                    )
        if self.hunger_increase_per_tick < 0.0:
            raise MonsterTemplateValidationException(
                f"hunger_increase_per_tick cannot be negative: {self.hunger_increase_per_tick}"
            )
        if self.hunger_decrease_on_prey_kill < 0.0:
            raise MonsterTemplateValidationException(
                f"hunger_decrease_on_prey_kill cannot be negative: {self.hunger_decrease_on_prey_kill}"
            )
        if not (0.0 <= self.hunger_starvation_threshold <= 1.0):
            raise MonsterTemplateValidationException(
                f"hunger_starvation_threshold must be between 0.0 and 1.0: {self.hunger_starvation_threshold}"
            )
        if self.starvation_ticks < 0:
            raise MonsterTemplateValidationException(
                f"starvation_ticks cannot be negative: {self.starvation_ticks}"
            )
        if self.max_age_ticks is not None and self.max_age_ticks < 0:
            raise MonsterTemplateValidationException(
                f"max_age_ticks cannot be negative: {self.max_age_ticks}"
            )
        if not (0.0 <= self.forage_threshold <= 1.0):
            raise MonsterTemplateValidationException(
                f"forage_threshold must be between 0.0 and 1.0: {self.forage_threshold}"
            )
        if self.hunger_decrease_on_feed < 0.0:
            raise MonsterTemplateValidationException(
                f"hunger_decrease_on_feed cannot be negative: {self.hunger_decrease_on_feed}"
            )

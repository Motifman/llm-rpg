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
    TemperatureDiscomfortKind,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum


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
    # Phase 4b PR (c): CHASE で BFS が探索する最大 hop 数。これより遠い target
    # spot / last_observed_target_spot_id は到達不可扱いとして CHASE を諦める。
    # 0 なら距離制限なし (グラフ全体を探索)。小さい値 (1-3) で「近距離型」、
    # 大きい値 (10-) で「執念深い長距離型」を表現。
    #
    # 注意: 「target に向かう移動」と「target を見失った後 last_observed に
    # 駆け付ける移動」の両方に同じ距離制限が適用される。これは「monster の
    # 視野外まで離れたら諦める」という単純化した世界観に基づく。
    #
    # `0` の意味は他の `*_ticks` フィールドと逆 (flee_grace_ticks=0 は即時忘却
    # = 反応しない、こちらは無制限) なので注意。これは「上限値」フィールドの
    # 直感に合わせた選択。
    chase_max_distance: int = 5
    # Phase 4b PR (c): CHASE 状態に入ってからの累積 tick 上限。これを **超えたら**
    # (>) 諦めて IDLE 復帰。ちょうど `chase_max_ticks` 経過時点はまだ継続、
    # `chase_max_ticks + 1` で初めて IDLE 化する (grace 切れ判定と統一した境界)。
    # 0 なら tick 制限なし。`flee_grace_ticks` (被弾以来の反応 tick) とは別軸で、
    # 「最初の被弾は古いが CHASE がまだ続く」状況での諦め基準として使う。
    chase_max_ticks: int = 20
    # Phase 4-O B: 環境温度に対する快適範囲。`min` 未満 / `max` 超過の spot
    # に居ると毎 tick `temperature_discomfort_damage_per_tick` HP 減少
    # (severity 比較で判定、enum 値順序ではない)。
    # default は FREEZING-HOT で「全温度で快適」(従来挙動互換)。
    min_comfortable_temperature: TemperatureEnum = TemperatureEnum.FREEZING
    max_comfortable_temperature: TemperatureEnum = TemperatureEnum.HOT
    # 不快温度 1 tick あたりの HP 減少量。0 で無効化 (default)。1-3 程度で
    # 「数十 tick で死ぬ」緩やかな圧、5+ で「直ぐ逃げないと死ぬ」強い圧。
    temperature_discomfort_damage_per_tick: int = 0
    # Phase 4-O C: pack 援護の最大距離 (BFS hop)。仲間が殴られたとき、自分が
    # この hop 数以内に居れば援護に駆け付ける。0 で援護機能無効 (default、
    # 後方互換)。1-3 で「近くの仲間だけ反応」、5+ で「広範囲援護」。
    pack_help_radius: int = 0
    # 1 つの援護要請に対して最大何匹が応答するかの上限。pack 全員が一斉に
    # 来ると 10 匹単位の大惨事になるため、シナリオ作成側が制御できるように
    # する。0 だと援護機能無効。
    max_pack_responders: int = 2
    # Phase 4-O C #2: pack leader の FLEE に追従するかどうか。True にすると、
    # 同 pack の leader が FLEE 状態に入ったら自分も連動して FLEE する。
    # default False で機能無効 (後方互換)。「リーダーが逃げると群れも崩れる」
    # 演出に使う。leader 自身は本フィールドの値に関わらず通常の FLEE 経路で
    # 入る (= leader 用フラグではなく follower 用フラグ)。
    pack_flee_follower: bool = False
    # follower が leader の FLEE に追従する際の FLEE 持続 tick 数。0 だと
    # 機能無効。leader と同じ flee_grace_ticks を使うと leader の grace が
    # 短い場合に follower が即抜けるため、follower 用の独立した値を持つ。
    pack_flee_follower_duration: int = 5

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
        if not isinstance(self.chase_max_distance, int) or isinstance(
            self.chase_max_distance, bool
        ):
            raise MonsterTemplateValidationException(
                "chase_max_distance must be int"
            )
        if self.chase_max_distance < 0:
            raise MonsterTemplateValidationException(
                f"chase_max_distance must be >= 0, got {self.chase_max_distance}"
            )
        if not isinstance(self.chase_max_ticks, int) or isinstance(
            self.chase_max_ticks, bool
        ):
            raise MonsterTemplateValidationException(
                "chase_max_ticks must be int"
            )
        if self.chase_max_ticks < 0:
            raise MonsterTemplateValidationException(
                f"chase_max_ticks must be >= 0, got {self.chase_max_ticks}"
            )
        if not isinstance(self.min_comfortable_temperature, TemperatureEnum):
            raise MonsterTemplateValidationException(
                "min_comfortable_temperature must be TemperatureEnum, "
                f"got {type(self.min_comfortable_temperature).__name__}"
            )
        if not isinstance(self.max_comfortable_temperature, TemperatureEnum):
            raise MonsterTemplateValidationException(
                "max_comfortable_temperature must be TemperatureEnum, "
                f"got {type(self.max_comfortable_temperature).__name__}"
            )
        if (
            self.min_comfortable_temperature.severity
            > self.max_comfortable_temperature.severity
        ):
            raise MonsterTemplateValidationException(
                f"min_comfortable_temperature ({self.min_comfortable_temperature}) "
                f"must be <= max ({self.max_comfortable_temperature})"
            )
        if not isinstance(
            self.temperature_discomfort_damage_per_tick, int,
        ) or isinstance(self.temperature_discomfort_damage_per_tick, bool):
            raise MonsterTemplateValidationException(
                "temperature_discomfort_damage_per_tick must be int"
            )
        if self.temperature_discomfort_damage_per_tick < 0:
            raise MonsterTemplateValidationException(
                "temperature_discomfort_damage_per_tick must be >= 0, "
                f"got {self.temperature_discomfort_damage_per_tick}"
            )
        if not isinstance(self.pack_help_radius, int) or isinstance(
            self.pack_help_radius, bool,
        ):
            raise MonsterTemplateValidationException(
                "pack_help_radius must be int"
            )
        if self.pack_help_radius < 0:
            raise MonsterTemplateValidationException(
                f"pack_help_radius must be >= 0, got {self.pack_help_radius}"
            )
        if not isinstance(self.max_pack_responders, int) or isinstance(
            self.max_pack_responders, bool,
        ):
            raise MonsterTemplateValidationException(
                "max_pack_responders must be int"
            )
        if self.max_pack_responders < 0:
            raise MonsterTemplateValidationException(
                f"max_pack_responders must be >= 0, got {self.max_pack_responders}"
            )
        if not isinstance(self.pack_flee_follower, bool):
            raise MonsterTemplateValidationException(
                "pack_flee_follower must be bool"
            )
        if not isinstance(self.pack_flee_follower_duration, int) or isinstance(
            self.pack_flee_follower_duration, bool,
        ):
            raise MonsterTemplateValidationException(
                "pack_flee_follower_duration must be int"
            )
        if self.pack_flee_follower_duration < 0:
            raise MonsterTemplateValidationException(
                "pack_flee_follower_duration must be >= 0, "
                f"got {self.pack_flee_follower_duration}"
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

    def temperature_discomfort(
        self, temperature: TemperatureEnum,
    ) -> Optional[TemperatureDiscomfortKind]:
        """指定温度が monster の comfort 範囲外なら不快タイプを返す。

        Returns:
            "too_cold": 温度が `min_comfortable_temperature` より低い
            "too_hot":  温度が `max_comfortable_temperature` より高い
            None: comfort 範囲内 (range の境界含む) または damage=0 で
                  そもそも不快効果が無効化されている
        """
        if self.temperature_discomfort_damage_per_tick <= 0:
            return None
        sev = temperature.severity
        if sev < self.min_comfortable_temperature.severity:
            return "too_cold"
        if sev > self.max_comfortable_temperature.severity:
            return "too_hot"
        return None

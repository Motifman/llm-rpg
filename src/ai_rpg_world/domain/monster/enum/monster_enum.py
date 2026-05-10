from enum import Enum


class MonsterStatusEnum(Enum):
    """モンスターの状態"""
    ALIVE = "alive"
    DEAD = "dead"
    RESPAWNING = "respawning"


class MonsterFactionEnum(Enum):
    """モンスターの派閥・敵対関係"""
    ENEMY = "enemy"      # 敵対（先制攻撃あり）
    NEUTRAL = "neutral"  # 中立（攻撃されるまで反撃しない）
    ALLY = "ally"        # 友好（プレイヤーの味方）


class DeathCauseEnum(Enum):
    """モンスター死亡原因（LLM・クエスト・報酬判定用）"""
    KILLED_BY_PLAYER = "killed_by_player"
    KILLED_BY_MONSTER = "killed_by_monster"
    STARVATION = "starvation"
    NATURAL = "natural"  # 寿命（Phase 7 用）
    ENVIRONMENT = "environment"  # Phase 4-O B: 温度・hazard 等の環境ダメージ


# Phase 4-O B: 環境温度による不快の種別。formatter / template / event で
# 共有する Literal 型。circular import を避けるため `Literal` で定義。
from typing import Literal as _Literal

TemperatureDiscomfortKind = _Literal["too_cold", "too_hot"]


class BehaviorStateEnum(Enum):
    """
    アクターの行動状態。

    主な遷移: 視界内にTHREAT→FLEE; 敵対でFLEEでない→CHASE(またはHP%でFLEE);
    ターゲット見失い→CHASE/ENRAGEはSEARCH, FLEEはRETURN; SEARCH終了→PATROLまたはRETURN;
    縄張り超過→RETURN; RETURN到着→IDLE; 移動失敗max回→RETURN; HP%≤phase→ENRAGE.
    """
    IDLE = "IDLE"       # 待機
    PATROL = "PATROL"   # 巡回
    CHASE = "CHASE"     # 追跡
    SEARCH = "SEARCH"   # 探索（見失った地点へ向かう）
    FLEE = "FLEE"       # 逃走
    RETURN = "RETURN"   # 初期位置への帰還
    ENRAGE = "ENRAGE"   # 怒り（ボス等のフェーズ状態）


class EcologyTypeEnum(Enum):
    """生態・行動タイプ（追跡・逃走・縄張りの振る舞い）"""
    NORMAL = "normal"           # 通常（発見したら追跡・HPで逃走）
    PATROL_ONLY = "patrol_only" # 巡回のみ（発見しても追わない）
    AMBUSH = "ambush"           # 待ち伏せ（初期位置から一定距離までしか追わない）
    FLEE_ONLY = "flee_only"     # 逃走専用（発見したら逃げるのみ）
    TERRITORIAL = "territorial" # 縄張り（初期位置から一定距離を超えたら帰還）


class ActiveTimeType(Enum):
    """活動時間帯（いつ行動するか）"""
    ALWAYS = "always"       # 常時活動
    DIURNAL = "diurnal"     # 昼行性（昼のみ）
    NOCTURNAL = "nocturnal"  # 夜行性（夜のみ）
    CREPUSCULAR = "crepuscular"  # 薄明性（朝・夕のみ）


class ReactionPolicyEnum(Enum):
    """攻撃を受けたときの反応 policy。

    Phase 4a で導入。`MonsterTemplate.reaction_to_attack` が読み、
    behavior tick service が `_react_to_attack` で実行する。

    `EcologyTypeEnum` (通常時の habit) と直交する軸で、reactive 行動だけを
    担う。例: 鹿は ecology=NORMAL + reaction=ALWAYS_FLEE、ボスは
    ecology=AMBUSH + reaction=ALWAYS_RETALIATE。
    """

    PASSIVE = "passive"                    # 反応しない（既存挙動・既定）
    ALWAYS_FLEE = "always_flee"            # 攻撃されたら必ず逃走
    ALWAYS_RETALIATE = "always_retaliate"  # 攻撃されたら必ず反撃
    FLEE_WHEN_LOW_HP = "flee_when_low_hp"  # HP < flee_threshold で逃走、それ以外は反撃


class TemperamentEnum(Enum):
    """モンスターの「性格」プリセット。Phase 4b PR (d)。

    `reaction_to_attack` / `flee_grace_ticks` / `chase_max_distance` /
    `chase_max_ticks` / `chase_search_ticks` / `flee_threshold` の組み合わせ
    に名前を付けて宣言的に表現するための enum。

    `apply_temperament(base_template, temperament)` で base template の各
    フィールドが temperament の値で上書きされる (dataclasses.replace)。
    既に明示的に値を設定したフィールドも上書きされるため、temperament で
    一括設定したい場合に使う。個別に微調整したい場合は apply 後に
    `dataclasses.replace(template, ...)` で上書きする。
    """

    PASSIVE_BEAST = "passive_beast"      # 攻撃しない平和な動物 (羊・うさぎ)
    COWARD = "coward"                    # 弱気、被弾即逃走 (子兎・ネズミ)
    WARY = "wary"                        # 警戒型、HP 低いと逃走 (野生動物)
    AGGRESSIVE = "aggressive"            # 普通の敵、追跡型 (オオカミ・オーク)
    FEROCIOUS = "ferocious"              # 執念深い長距離追跡型 (ボス・狂犬)
    BERSERKER = "berserker"              # 距離 / tick 無制限の暴走 (狂戦士)

from enum import Enum


class StatusEffectType(Enum):
    """ステータス異常・強化の種類"""
    ATTACK_UP = "attack_up"
    ATTACK_DOWN = "attack_down"
    DEFENSE_UP = "defense_up"
    DEFENSE_DOWN = "defense_down"
    SPEED_UP = "speed_up"
    SPEED_DOWN = "speed_down"
    REGENERATION = "regeneration"
    POISON = "poison"
    # PR #2: 元々 PARALYSIS = "poison" だった typo を "paralysis" に修正。
    # 既存 caller (LLM プロンプト等) は POISON / PARALYSIS を文字列ではなく
    # enum で扱っているはずだが、もし str 値で永続化していたら互換注意。
    PARALYSIS = "paralysis"  # 移動不可など
    STUN = "stun"  # 行動不可
    # PR #2 survival 拡張: 漂流島 v2 で使う状態異常。各々 tick 駆動で HP に
    # 影響したり、行動を制限したりする。
    BLEEDING = "bleeding"  # 出血: tick 毎 HP -1, 救急用品 or 時間で治癒
    HYPOTHERMIA = "hypothermia"  # 低体温: 寒い spot で tick 毎 HP -1
    EXHAUSTED = "exhausted"  # 極度疲労: FATIGUE 100% で発症、行動効率低下
    INFECTED = "infected"  # 感染症: 傷を放置で発症、tick 毎 HP -1 (BLEEDING より遅い)

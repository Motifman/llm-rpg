"""
モンスターのスキル簡略情報。
AIの行動判断（スキル選択ポリシー）で利用する読み取り専用の値オブジェクト。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MonsterSkillInfo:
    """AIが判断に利用するためのスキル簡略情報"""
    slot_index: int
    range: int
    mp_cost: int

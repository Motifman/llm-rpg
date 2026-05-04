"""エージェントの欲求（ニーズ）値オブジェクト。

0（完全に満たされている）〜 max_value（限界）の範囲で管理する。
値が高いほど「満たされていない」= 行動の動機が強い。
tick経過で自然増加し、対応する行動（食事、睡眠等）で回復（値が下がる）する。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NeedType(Enum):
    HUNGER = "HUNGER"      # 空腹: tick経過で増加、食事で回復
    FATIGUE = "FATIGUE"    # 疲労: tick経過・行動で増加、睡眠で回復


@dataclass(frozen=True)
class AgentNeed:
    """単一の欲求の値オブジェクト。"""

    need_type: NeedType
    value: int       # 0 = 完全に満たされている, max_value = 限界
    max_value: int

    def __post_init__(self) -> None:
        if self.max_value <= 0:
            raise ValueError(f"max_value must be positive: {self.max_value}")
        if self.value < 0 or self.value > self.max_value:
            raise ValueError(
                f"value must be 0..{self.max_value}: {self.value}"
            )

    @classmethod
    def create(cls, need_type: NeedType, value: int, max_value: int) -> AgentNeed:
        """値を範囲内にクランプして生成する。"""
        actual = max(0, min(value, max_value))
        return cls(need_type=need_type, value=actual, max_value=max_value)

    def increase(self, amount: int) -> AgentNeed:
        """欲求を増加させる（満たされていない方向へ）。"""
        if amount < 0:
            raise ValueError(f"increase amount must be non-negative: {amount}")
        return AgentNeed.create(self.need_type, self.value + amount, self.max_value)

    def satisfy(self, amount: int) -> AgentNeed:
        """欲求を満たす（値を下げる）。"""
        if amount < 0:
            raise ValueError(f"satisfy amount must be non-negative: {amount}")
        return AgentNeed.create(self.need_type, self.value - amount, self.max_value)

    @property
    def percentage(self) -> float:
        """欲求の充足度（0.0 = 完全充足, 1.0 = 限界）。"""
        return self.value / self.max_value

    @property
    def is_critical(self) -> bool:
        """欲求が危険レベル（80%以上）か。"""
        return self.percentage >= 0.8

    @property
    def is_high(self) -> bool:
        """欲求が高い（60%以上）か。"""
        return self.percentage >= 0.6

    @property
    def is_satisfied(self) -> bool:
        """欲求が十分に満たされている（20%以下）か。"""
        return self.percentage <= 0.2

    def describe(self) -> str:
        """欲求の状態を自然言語で返す。"""
        pct = self.percentage
        label = "空腹" if self.need_type == NeedType.HUNGER else "疲労"
        if pct >= 0.8:
            return f"{label}: 危険（{self.value}/{self.max_value}）"
        if pct >= 0.6:
            return f"{label}: 高い（{self.value}/{self.max_value}）"
        if pct >= 0.4:
            return f"{label}: やや感じる（{self.value}/{self.max_value}）"
        if pct >= 0.2:
            return f"{label}: 少し（{self.value}/{self.max_value}）"
        return f"{label}: 問題なし（{self.value}/{self.max_value}）"

    def __str__(self) -> str:
        return f"{self.need_type.value}: {self.value}/{self.max_value}"

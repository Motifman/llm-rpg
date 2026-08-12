"""エージェントの欲求（ニーズ）値オブジェクト。

0（完全に満たされている）〜 max_value（限界）の範囲で管理する。
値が高いほど「満たされていない」= 行動の動機が強い。
tick経過で自然増加し、対応する行動（食事、睡眠等）で回復（値が下がる）する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class NeedType(Enum):
    HUNGER = "HUNGER"      # 空腹: tick経過で増加、食事で回復
    FATIGUE = "FATIGUE"    # 疲労: tick経過・行動で増加、睡眠で回復


#: 欲求 → 表示上の呼び名。**全件持つ (網羅テストが縛る)。**
#:
#: 以前は ``"空腹" if need_type == HUNGER else "疲労"`` の 2 分岐だった。**HUNGER
#: 以外を全部「疲労」と表示する**形で、NeedType が 2 つしかないから偶然正しかった
#: だけである。渇き (THIRST) を足したら「疲労: 危険」と出る。
#:
#: なお呼び名そのものの所有者 (コード / シナリオ) は別の論点で #1054 の判断待ち。
#: ここでは 2 分岐を表へ集約するだけで、所有者は変えていない。
_NEED_LABELS: "dict[NeedType, str]" = {
    NeedType.HUNGER: "空腹",
    NeedType.FATIGUE: "疲労",
}


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

    def describe(self, delta: Optional[int] = None) -> str:
        """欲求の状態を自然言語で返す。

        PR-T: ``delta`` が渡され非 0 のとき、末尾に「前回 +N」または「前回 -N」
        の trajectory 情報を追記する。これにより LLM が「改善中 / 悪化中」を
        能動的に追える。0 や None は従来挙動 (= 末尾追記なし)。
        """
        pct = self.percentage
        label = _NEED_LABELS[self.need_type]
        if pct >= 0.8:
            tier = "危険"
        elif pct >= 0.6:
            tier = "高い"
        elif pct >= 0.4:
            tier = "やや感じる"
        elif pct >= 0.2:
            tier = "少し"
        else:
            tier = "問題なし"
        base = f"{label}: {tier}（{self.value}/{self.max_value}）"
        if delta is None or delta == 0:
            return base
        # delta > 0 は「悪化」(= 疲労が増えた / 空腹が進んだ)、< 0 は「改善」。
        # 直前 turn からの変化を ``前回 +N`` / ``前回 -N`` で示す。
        sign = "+" if delta > 0 else ""
        return f"{base}、前回 {sign}{delta}"

    def __str__(self) -> str:
        return f"{self.need_type.value}: {self.value}/{self.max_value}"

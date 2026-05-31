"""プレイヤー個別の終局 outcome (Phase E-3)。

設計 §6 に基づくプレイヤーごとの終局状態。集団勝敗 (GameResultEnum)
ではなく、個別 outcome として並列に保持する。

- UNRESOLVED: 未確定。シナリオ初期状態。
- RESCUED: 救助された。
- DEAD: HP 0 で戦闘不能になった。
- STRANDED: tick 上限に達したが救助されなかった (取り残された)。

UNRESOLVED 以外はすべて「終局状態」と扱う (再遷移しない)。
"""

from __future__ import annotations

from enum import Enum


class PlayerOutcomeEnum(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESCUED = "RESCUED"
    DEAD = "DEAD"
    STRANDED = "STRANDED"

    @property
    def is_resolved(self) -> bool:
        """UNRESOLVED 以外なら True (= 終局状態)。"""
        return self is not PlayerOutcomeEnum.UNRESOLVED

    @property
    def display_label(self) -> str:
        """LLM プロンプト等への日本語表示用。"""
        return {
            PlayerOutcomeEnum.UNRESOLVED: "未確定",
            PlayerOutcomeEnum.RESCUED: "救助",
            PlayerOutcomeEnum.DEAD: "死亡",
            PlayerOutcomeEnum.STRANDED: "取り残され",
        }[self]

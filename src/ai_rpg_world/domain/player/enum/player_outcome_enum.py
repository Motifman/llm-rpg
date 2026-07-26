"""プレイヤー個別の終局 outcome (Phase E-3)。

設計 §6 に基づくプレイヤーごとの終局状態。集団勝敗 (GameResultEnum)
ではなく、個別 outcome として並列に保持する。

- UNRESOLVED: 未確定。シナリオ初期状態。
- RESCUED: 救助された。
- DEAD: HP 0 で戦闘不能になった。
- EJECTED: 会議の投票で追放された。
- STRANDED: tick 上限に達したが救助されなかった (取り残された)。

UNRESOLVED 以外はすべて「終局状態」と扱う (再遷移しない)。
"""

from __future__ import annotations

from enum import Enum


class PlayerOutcomeEnum(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESCUED = "RESCUED"
    DEAD = "DEAD"
    #: 会議の投票で追放された。DEAD と混ぜない。
    #:
    #: 分析で「殺されたのか追放されたのか」を読み分けたい。それ以上に、
    #: 陣営の勝敗条件が「DEAD 以外は生存」で数えているので、混ぜずに足した
    #: だけだと追放された相手が生存側へ回り、全滅が永久に成立しなくなる。
    EJECTED = "EJECTED"
    STRANDED = "STRANDED"

    @property
    def is_resolved(self) -> bool:
        """UNRESOLVED 以外なら True (= 終局状態)。"""
        return self is not PlayerOutcomeEnum.UNRESOLVED

    @property
    def is_eliminated(self) -> bool:
        """力ずくで盤から排除されたか。

        「もう盤上に居ないか」を聞く箇所 (表示 / give_item の可否 /
        tend_to_player の可否 / 陣営の生存数) はここを見る。各所で
        ``is DEAD`` を直接書くと、**メンバを足したときに全部が黙って
        取りこぼす**。

        RESCUED と STRANDED は盤から降りてはいるが、力ずくで排除された
        わけではないので False。陣営の全滅判定で「殺された」と同じに数えると、
        救助された仲間の数だけ全滅が早まる。
        """
        return self in (PlayerOutcomeEnum.DEAD, PlayerOutcomeEnum.EJECTED)

    @property
    def display_label(self) -> str:
        """LLM プロンプト等への日本語表示用。"""
        return {
            PlayerOutcomeEnum.UNRESOLVED: "未確定",
            PlayerOutcomeEnum.RESCUED: "救助",
            PlayerOutcomeEnum.DEAD: "死亡",
            PlayerOutcomeEnum.EJECTED: "追放",
            PlayerOutcomeEnum.STRANDED: "取り残され",
        }[self]

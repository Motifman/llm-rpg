"""強く出ている欲求から、意味記憶の検索語を決める。

## なぜ要るか (系統2)

`prompt_builder` は検索語を決めるのに、**自分たちが組み立てた表示文を読み直して
いた**。

    for line in snap.need_lines:                    # "空腹: 危険（68/100、前回 +3）"
        if line.startswith("空腹") and ("高い" in line or "危険" in line):
            out.extend(("空腹", "食料"))

判定に必要な値はドメインに既にある。

    AgentNeed.need_type          -> 「空腹で始まるか」で代用していた
    AgentNeed.is_high (>= 0.6)   -> 「高い or 危険 を含むか」で代用していた

``("高い" in line or "危険" in line)`` は `is_high` と**完全に等価**である
(`describe` の tier が 0.6 以上で「高い」、0.8 以上で「危険」)。既にある述語を
文字列で再実装していた。

**表示の言い回しを変えると検索語が消える。** tier を「高い」から「強い」に直す
リファクタリングで、想起の手がかりが黙って出なくなる。テストは通る。

#380 (系統1) と同じ形。あちらはシナリオ作者の自由文に依存し、こちらは自分の表示文に
依存していた。どちらも**値を持っているのに文字列から読み直していた**。

## 呼び名の所有者はここでは変えない

「空腹」「食料」という語がコードにあること自体は別の論点で、#1054 の判断待ち。
`NeedType` は engine の enum なので、いまはコードが既定を持つ。アンドロイドが主体の
世界を作るなら「空腹」は嘘になるので、そのとき宣言へ移す。
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType

__all__ = ["RECALL_CUES_BY_NEED_TYPE", "recall_cues_for_needs"]

#: 欲求 → その欲求が強いときに意味記憶を探す語。**全件持つ (網羅テストが縛る)。**
#:
#: 旧実装が出していた語をそのまま使う (挙動不変)。載せ忘れると、その欲求が危険域でも
#: 手がかりが黙って出なくなる。
RECALL_CUES_BY_NEED_TYPE: Dict[NeedType, Tuple[str, ...]] = {
    NeedType.HUNGER: ("空腹", "食料"),
    NeedType.FATIGUE: ("疲労", "休息"),
}


def recall_cues_for_needs(needs: Iterable[AgentNeed]) -> Tuple[str, ...]:
    """強く出ている欲求の検索語を、宣言順で重複なく返す。

    閾値は `AgentNeed.is_high` (60% 以上) に委ねる。**閾値をここに書き写さない。**
    書き写すと、ドメインが閾値を変えたときに片方だけ古くなる。
    """
    cues: list[str] = []
    for need in needs or ():
        if not getattr(need, "is_high", False):
            continue
        for cue in RECALL_CUES_BY_NEED_TYPE.get(need.need_type, ()):
            if cue not in cues:
                cues.append(cue)
    return tuple(cues)

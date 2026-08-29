"""前提条件を「見せてよいもの」と「隠すべきもの」に分ける。

## なぜ要るか

満たしていない前提条件は、既定では「いまできない: 〜」として候補に残す。
理由まで見せたほうが、存在しない操作名を発明されるより良いから
(`_interaction_blocking_hints` の判断)。

**役割で弾かれる条件だけは違う。** `station_drill` の実 run で、crew の
行動候補にこう出ていた。

    [配線の結束を締め直す (tighten_wiring),
     配線の結束を締め直す (tighten_wiring_pretend)]

`tighten_wiring_pretend` は keeper 専用の偽装版。crew は自分の候補を読む
だけで「この作業には偽装版がある」と分かってしまう。**役割を伏せる意味が
薄れる。** 「いまできない」に回しても、存在することは伝わるので同じ。

だから条件の種類ごとに、満たせないときの扱いを宣言する。

## 分け方

- ``PUBLIC``: 満たしていない理由を見せてよい。物理的・環境的な条件
  (暗すぎる / 部品が無い / 扉が閉じている)。見せたほうが次の手を選べる
- ``HIDDEN``: 存在ごと隠す。**誰が何者か**に依存する条件。見せると、
  伏せてあるはずの役割構造が候補一覧から読めてしまう

#860 で同席者の行に置いた不変条件と同じ考え方:
**その行に出す判断の材料は、見る人に既に見えている事実だけに限る。**
"""

from __future__ import annotations

from enum import Enum

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)


class ConditionVisibility(Enum):
    """満たしていない前提条件を、候補一覧でどう扱うか。"""

    #: 「いまできない: 〜」として候補に残し、理由を見せる。
    PUBLIC = "PUBLIC"
    #: 候補ごと消す。条件の存在自体が伏せるべき情報を漏らす。
    HIDDEN = "HIDDEN"


#: 条件の種類ごとの扱い。
#:
#: **新しい条件を足したら、ここにも足す。** 足し忘れは
#: ``tests/domain/world_graph/test_interaction_condition_visibility.py``
#: が起動時ではなくテストで止める。既定を PUBLIC にすると、秘匿すべき条件を
#: 足した人が何も言われないまま漏らすことになる。
CONDITION_VISIBILITY: dict[InteractionConditionTypeEnum, ConditionVisibility] = {
    # --- 誰が何者かに依存する。存在ごと隠す ---
    #
    # 行為者の自由 state。役割 (role=keeper) のような伏せた属性がここに入る。
    InteractionConditionTypeEnum.PLAYER_STATE_IS: ConditionVisibility.HIDDEN,
    # 対象の自由 state。対象の役割で出し分ける行為 (襲撃など) が該当する。
    InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS: ConditionVisibility.HIDDEN,
    # --- 物理・環境・持ち物。理由を見せたほうが次の手を選べる ---
    InteractionConditionTypeEnum.ALWAYS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.HAS_ITEM: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.HAS_ITEMS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.OBJECT_STATE: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.FLAG_SET: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.FLAG_NOT_SET: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PLAYERS_AT_SPOT: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PREPARED_ACTION: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PUZZLE_INPUT_MATCH: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.ITEM_INSTANCE_STATE: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PLAYER_GOLD_AT_LEAST: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.TIME_OF_DAY_IS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.WEATHER_IS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.WEATHER_IS_NOT: ConditionVisibility.PUBLIC,
    # 明るさ・場所は、その場に居れば見えている事実。隠す理由が無い。
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.AT_SPOT_IS: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.AT_SPOT_IS_NOT: ConditionVisibility.PUBLIC,
    InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST: ConditionVisibility.PUBLIC,
    # 倒れているかは同席者行に出ている公開事実 (#860)。
    InteractionConditionTypeEnum.TARGET_PLAYER_IS_INCAPACITATED: (
        ConditionVisibility.PUBLIC
    ),
    # 対象の持ち物は**見えていない**。「奪える／奪えない」が候補に出ると、
    # 持ち物を覗いたのと同じ情報が漏れる。倒れた相手を漁る行為 (#837 の
    # loot_from_downed) が該当する。
    InteractionConditionTypeEnum.TARGET_HAS_ITEM: ConditionVisibility.HIDDEN,
    InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM: ConditionVisibility.HIDDEN,
}


def is_hidden(condition_type: InteractionConditionTypeEnum) -> bool:
    """その条件は、満たせないときに候補ごと隠すべきか。

    宣言の無い種類は **隠す側** に倒す。既定を「見せる」にすると、秘匿すべき
    条件を足した人が気づかないまま漏らす。逆に倒せば、足し忘れは「候補が
    出ない」として作者に見える。
    """
    return CONDITION_VISIBILITY.get(condition_type, ConditionVisibility.HIDDEN) is (
        ConditionVisibility.HIDDEN
    )

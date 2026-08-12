"""前提条件の失敗を、シナリオ宣言から区分する。

## なぜ要るか (#380)

`interact` の失敗 remediation は、**シナリオ作者が書いた自由文**を日本語キーワードで
部分一致検索して切り替えていた。

    _INTERACTION_EXHAUST_HINTS = ("採り尽く", "枯渇", "もう空", "もう開い",
                                  "すでに", "今は", "燃え上が")

`failure_message` は「エージェントに読ませる文」として書かれているのに、**分類キー
としても二重に使われていた**。作者は自分の言い回しがシステムの分岐を変えることを
知らない。「集めた」を「採り尽くした」に直すだけで挙動が変わる。

## 実測: 当たっても外れても害だった

実 run 43 本の `INTERACTION_PRECONDITION_FAILED` 679 件の内訳。

    時間で回復  251 件 ... うちキーワード当たり 31 件 (**その 31 件は全部誤り**)
    前提不足    216 件 ... 当たらず (正しい)
    恒久的      154 件 ... うち当たり 43 件 (28%)
    照合できず   62 件 ... 引数不足 / クールダウン / 対人 action (別経路)

「時間で回復」の 88% を取りこぼし、当たった分は**逆の助言**をしていた。「同じ object
に再試行しても結果は変わらない。別の場所を選べ」と返すが、実際は待てば回復する。
作者は `failure_message` に「風がまた運んでくるのを待つしかない」と書いているのに、
システムがその上から「待つな」を重ねていた。実 run で同じ壁に **96 回**当たっている。

## 区分は宣言から導ける

キーワードは要らない。失敗した条件と `reactive_bindings` を突き合わせる。

    失敗条件:  OBJECT_STATE / fallen_leaves / {"available": True} を要求
    binding :  OBJECT_STATE_TICK_AT_LEAST(fallen_leaves, last_harvest_tick, +24)
               → on_true_state_updates {"available": True}

**同じ物体・同じ state_key・要求値と一致**を時間述語が戻すなら「時間で回復」。

## 待ち時間は出さない

binding は ``ticks_offset`` を持っているので「あと 24 tick」と言えるが、``tick`` は
エージェントの語彙ではない。世界時刻の表示は別にあるので、ここでは「待てば戻る」
までに留める。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, Optional, Sequence

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)

__all__ = [
    "PreconditionFailureKind",
    "REMEDIATION_BY_KIND",
    "classify_precondition_failure",
    "remediation_for_precondition_failure",
]

#: 物体の状態を見る条件の種別。これ以外は `reactive_bindings` と関係が無い。
#:
#: 実測すると ``required_state`` を持つ前提条件は ``OBJECT_STATE`` だけ (159 件)。
#: ``OBJECT_STOCK_AT_LEAST`` / ``OBJECT_STATE_INT_AT_LEAST`` は数量条件で
#: ``required_state`` を持たないため、binding の state 更新と突き合わせられない。
#: それらを含めても照合が成立しないので、対象から外して
#: ``MISSING_PREREQUISITE`` へ倒す。
_OBJECT_STATE_CONDITIONS = frozenset(
    {InteractionConditionTypeEnum.OBJECT_STATE}
)

#: 述語のうち「時間経過だけで真になる」もの。
#:
#: 名前で判定するのは、`ScenarioEventCondition.condition_type` が str であり
#: 集中 enum を持たないため。`TICK_AT_LEAST` を含む種別は tick を材料にする。
_TIME_PREDICATE_MARKER = "TICK_AT_LEAST"


class PreconditionFailureKind(Enum):
    """前提条件の失敗を、次に取るべき手で分ける。"""

    #: 待てば世界の側が状態を戻す。**同じ対象へ戻ってくるのが正しい。**
    TIME_RECOVERING = "time_recovering"
    #: 別の条件が満たされたときに戻る (誰かの行動 / フラグ / 天候)。
    CONDITION_RECOVERING = "condition_recovering"
    #: 戻す宣言が無い。別の対象を選ぶのが正しい。
    PERMANENT = "permanent"
    #: 持ち物・体力・天候などの前提が足りない。揃えてから戻る。
    MISSING_PREREQUISITE = "missing_prerequisite"


#: 区分 → エージェントへ返す助言。**全区分に文を持つ (網羅テストが縛る)。**
#:
#: 文に英字の識別子を混ぜないこと。#1043 で閉じた「ID をプロンプトに出さない」
#: 方針の裏口になる。
REMEDIATION_BY_KIND: Dict[PreconditionFailureKind, str] = {
    PreconditionFailureKind.TIME_RECOVERING: (
        "時間が経てば元に戻る。いま繰り返しても変わらないので、"
        "他のことをして待ってから戻ること。"
    ),
    PreconditionFailureKind.CONDITION_RECOVERING: (
        "状況が変われば通るようになる。何が足りないのかを確かめるか、"
        "先に別の手を打ってから戻ること。"
    ),
    PreconditionFailureKind.PERMANENT: (
        "ここはもう変わらない。同じ相手に同じことを繰り返さず、"
        "別の場所か別の対象を選ぶこと。"
    ),
    PreconditionFailureKind.MISSING_PREREQUISITE: (
        "足りない前提を先に満たすこと。"
        "失敗の説明に名指しされた持ち物や状態を確かめること。"
    ),
}


def _iter_predicate_types(predicate: Any) -> Iterable[str]:
    """述語木の全 `condition_type` を列挙する。

    合成述語 (AND / OR / NOT) の中に時間条件が入る形が実在する
    (cauldron_crafting の ``AND(OBJECT_STATE, OBJECT_STATE_TICK_AT_LEAST)``)。
    leaf だけ見ると取りこぼす。
    """
    if predicate is None:
        return
    yield str(getattr(predicate, "condition_type", "") or "")
    for child in getattr(predicate, "children", ()) or ():
        yield from _iter_predicate_types(child)


def _restores(binding: Any, state_key: str, required_value: Any) -> bool:
    """この binding が ``state_key`` を ``required_value`` へ書くか。"""
    for updates in (
        getattr(binding, "on_true_state_updates", ()) or (),
        getattr(binding, "on_false_state_updates", ()) or (),
    ):
        for key, value in updates:
            if key == state_key and value == required_value:
                return True
    return False


def classify_precondition_failure(
    condition: Any,
    *,
    bindings: Sequence[Any] = (),
) -> PreconditionFailureKind:
    """失敗した条件を、シナリオ宣言だけを見て区分する。

    ``condition`` が無い / 物体状態でないなら ``MISSING_PREREQUISITE`` へ倒す。
    **既定を「揃えてから再試行」にするのは、最も無害だから。** 「待て」や
    「別の対象へ」を既定にすると、成立しうる行動を諦めさせる。
    """
    if condition is None:
        return PreconditionFailureKind.MISSING_PREREQUISITE
    if getattr(condition, "condition_type", None) not in _OBJECT_STATE_CONDITIONS:
        return PreconditionFailureKind.MISSING_PREREQUISITE

    target_object_id = getattr(condition, "target_object_id", None)
    required_state = getattr(condition, "required_state", None) or {}
    if target_object_id is None or not required_state:
        return PreconditionFailureKind.MISSING_PREREQUISITE

    found_non_time_restore = False
    for binding in bindings or ():
        if getattr(binding, "target_object_id", None) != target_object_id:
            continue
        for state_key, required_value in required_state.items():
            if not _restores(binding, state_key, required_value):
                continue
            if any(
                _TIME_PREDICATE_MARKER in kind
                for kind in _iter_predicate_types(getattr(binding, "predicate", None))
            ):
                return PreconditionFailureKind.TIME_RECOVERING
            found_non_time_restore = True

    if found_non_time_restore:
        return PreconditionFailureKind.CONDITION_RECOVERING
    return PreconditionFailureKind.PERMANENT


def remediation_for_precondition_failure(
    condition: Any,
    *,
    bindings: Sequence[Any] = (),
) -> str:
    """失敗した条件に対する助言文を返す。"""
    return REMEDIATION_BY_KIND[
        classify_precondition_failure(condition, bindings=bindings)
    ]

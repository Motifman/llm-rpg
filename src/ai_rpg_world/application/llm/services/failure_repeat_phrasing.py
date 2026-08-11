"""反復した失敗を、エージェントの語彙で言い表す。

## なぜ要るか

反復失敗は意味記憶の証拠 (``BeliefEvidence``) に転記される。以前はその本文に
**error_code をそのまま埋めていた**。

    「interact」が「INTERACTION_PRECONDITION_FAILED」を3回反復した。

``INTERACTION_PRECONDITION_FAILED`` はエージェントの語彙ではない。実 run の
``belief_consolidation`` を読むと、統合を判断する LLM がこの証拠を「システム
エラーの繰り返しであり、学習すべき内容ではない」と書いて捨てていた。**4 run で
独立に同じ判断が出ている。** 反復した失敗こそ学ぶ価値があるのに、内部識別子の
せいで機械的なノイズとして捨てられていた。

CLAUDE.md の「プロンプト本文にツール名を書くときは必ず露出判断を通す」と同じ形。
**内部の識別子が、エージェントの読む面へ漏れている。**

## なぜ全 code を網羅しないか

``error_code`` の集中 enum は存在せず、``error_code="..."`` のリテラルが 67 種類
ソースに散在している。全部そろえるのは重い。そこで

- 実 run で出た 16 種類には個別の言い換えを書く
- それ以外は **code を出さない汎用文へ倒す**

とする。粒度が粗くても、語彙が通じる方がよい。漏らさないことだけは
``test_failure_evidence_speaks_agent_vocabulary.py`` が確実に止める。

## 文面を足すときの決まり

- **英大文字の識別子を書かない** (テストが落とす)
- 「何に阻まれたか」が分かる言い方にする。「失敗した」だけでは次の手を選べない
- ツール名と回数は呼び出し側が付けるので、ここには書かない
"""

from __future__ import annotations

from typing import Dict

__all__ = ["describe_repeated_failure"]

#: error_code → 反復したときの言い方 (「〜」に入る部分)。
#:
#: 実 run で証拠になったのは ``INTERACTION_PRECONDITION_FAILED`` (41 件) と
#: ``INVALID_TARGET_LABEL`` (9 件) の 2 つ。残りは反復に至っていないが、同じ
#: 経路を通るので実測で出た 16 種類すべてに書いてある。
_REPEATED_FAILURE_PHRASING: Dict[str, str] = {
    # --- 対象や行き先の指し方が通らない ---
    "INVALID_TARGET_LABEL": "その名前の相手や物が見つからず",
    "INVALID_DESTINATION_LABEL": "その名前の行き先が見つからず",
    "INTERACTION_ACTION_NOT_FOUND": "その操作が対象に無く",
    "INVALID_ARGUMENT": "指定の書き方が通らず",
    # --- 前提条件・状態が満たされない ---
    "INTERACTION_PRECONDITION_FAILED": "同じ前提条件の不足に",
    "TARGET_NOT_INCAPACITATED": "相手がまだ動いていて",
    "ALREADY_VOTED": "すでに投票を終えていて",
    # --- 持ち物の容量 ---
    "GIVE_ITEM_TARGET_INVENTORY_FULL": "相手の持ち物が満杯で",
    "PICKUP_ITEM_SELF_INVENTORY_FULL": "自分の持ち物が満杯で",
    # --- アイテムの性質 ---
    "ITEM_NOT_CONSUMABLE": "それが食べ物ではないため",
    # --- ツールがその場で使えない ---
    "UNSUPPORTED_TOOL": "この世界にその手立てが無く",
    "TOOL_BECAME_UNAVAILABLE": "その手立てが使えなくなっていて",
    "TOOL_NOT_OFFERED_NOW": "今はその手立てを選べず",
    # --- 発話 ---
    "INVALID_SPEECH_CHANNEL": "その話し方が通らず",
    "INVALID_WHISPER": "囁く相手を指せず",
    # --- 覚え書き ---
    "TODO_ERROR": "覚え書きの操作が通らず",
}

#: 対応表に無い code のときの言い方。**code は出さない。**
_FALLBACK_PHRASING = "同じ理由で"


def describe_repeated_failure(*, tool_name: str, error_code: str, count: int) -> str:
    """反復した失敗を、エージェントが読める 1 文にする。

    ツール名と回数は事実として残す (cue が ``tool:<name>`` なので本文からツールが
    消えると照合できない。1 回の失敗と反復は意味が違うので回数も残す)。理由の
    部分だけを対応表で言い換える。

    対応表に無い code は ``_FALLBACK_PHRASING`` へ倒し、**code を本文へ出さない**。
    """
    reason = _REPEATED_FAILURE_PHRASING.get(error_code, _FALLBACK_PHRASING)
    return f"「{tool_name}」が{reason}{count}回続けて阻まれた。"

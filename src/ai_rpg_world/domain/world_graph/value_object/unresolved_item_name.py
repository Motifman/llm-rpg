"""相手の持ち物に当てられなかった品名を、前提条件の断りに載せる (design_decisions D1641)。

名前を当てる処理は前提条件より先に走る。そこで断ると、籠の中の相手のように
先に返すべき断りを追い越し、相手の持ち物の手がかりまで漏らす。だから当てられ
なかった理由を ``interaction_parameters`` に置き、``TARGET_HAS_ITEM`` が自分の
番で返す。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

UNRESOLVED_ITEM_NAME_KEY = "item_name_unresolved"
ITEM_NAME_KEY = "item"


class UnresolvedItemNameReason(str, Enum):
    AMBIGUOUS = "ambiguous"
    UNRECOGNIZED = "unrecognized"


def unresolved_item_name_message(parameters: Mapping[str, Any] | None) -> str | None:
    if not parameters:
        return None
    try:
        reason = UnresolvedItemNameReason(parameters.get(UNRESOLVED_ITEM_NAME_KEY))
    except ValueError:
        return None
    name = str(parameters.get(ITEM_NAME_KEY) or "").strip()
    if reason is UnresolvedItemNameReason.AMBIGUOUS:
        return (
            f"「{name}」に当てはまりそうな物が相手の持ち物に複数ある。"
            "どれを指すのか決められないので、品の名前をそのまま書くこと。"
        )
    return (
        f"「{name}」がどの品を指すのか、相手の持ち物から見分けられなかった。"
        "持っていないとは限らない。品の名前が違うのかもしれない。"
    )

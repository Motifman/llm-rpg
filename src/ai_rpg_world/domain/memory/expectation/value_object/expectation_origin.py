from __future__ import annotations

from enum import Enum


class ExpectationOrigin(str, Enum):
    """予期の出どころ。"""

    WITH_ACTION = "with_action"
    """行動に添えた予期。「箱を開けても空だろう」"""

    PROMISE_OR_OUTLOOK = "promise_or_outlook"
    """約束・見通し。「二日後に B と会う」"""

    FROM_BELIEF = "from_belief"
    """信念に照らして意外な出来事があったときに、裏切られた暗黙の予期を書き出したもの。"""


__all__ = ["ExpectationOrigin"]

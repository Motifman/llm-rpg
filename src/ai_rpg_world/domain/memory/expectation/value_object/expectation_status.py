from __future__ import annotations

from enum import Enum


class ExpectationStatus(str, Enum):
    """予期の状態。OPEN 以外はすべて終わりで、そこから先へは移らない。"""

    OPEN = "open"
    """清算待ち。最後の照合が当たった / 外れたなら、それが暫定の判定。"""

    SETTLED = "settled"
    """当否が確定した。信念を直す材料になる。"""

    DISMISSED = "dismissed"
    """形の判定で、清算できる形ではないとして外した。"""

    VOIDED = "voided"
    """照合で、予期になっていないと判定されて外した。"""

    EXPIRED = "expired"
    """当否が決まらないまま期限のターンを過ぎた。"""

    @property
    def is_open(self) -> bool:
        return self is ExpectationStatus.OPEN


__all__ = ["ExpectationStatus"]

from __future__ import annotations

from enum import Enum


class Likelihood(str, Enum):
    """本人が予期に付けた確からしさ。外れたときの驚きの大きさに使う。"""

    ALMOST_CERTAIN = "almost_certain"
    PROBABLY = "probably"
    EVEN = "even"
    MAYBE = "maybe"


__all__ = ["Likelihood"]

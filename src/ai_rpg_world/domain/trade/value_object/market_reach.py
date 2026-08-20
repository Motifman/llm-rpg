"""板の届く範囲 (経済統合 Phase 3)。

**板が場所にあるなら、板を使うことは「その場所に居ること」で、それは「そこに
居る他人と一緒に居ること」**になる。どんな地図を書いても板の前は待ち合わせ
場所になるので、地図では直らない。届く範囲そのものを世界の規則にする。

人狼系は ``AT_SPOT`` のまま。誰がいつどこに居たかが推理の材料なので、板の前に
立った事実を消せない。MMO 的な世界は ``GLOBAL``。**既定は ``AT_SPOT``** で、
宣言しない世界の挙動は変わらない。
"""

from __future__ import annotations

from enum import Enum


class MarketReach(Enum):
    """板がどこまで届くか。"""

    #: 板と同じ場所に居るときだけ使える。板の前が待ち合わせ場所になる。
    AT_SPOT = "at_spot"
    #: どこからでも使える。板の前に立つ必要が無い。
    GLOBAL = "global"

    @property
    def is_global(self) -> bool:
        return self is MarketReach.GLOBAL


__all__ = ["MarketReach"]

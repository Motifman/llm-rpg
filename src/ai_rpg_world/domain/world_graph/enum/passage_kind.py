"""スポット接続の通過形態（passage_kind）と、形態ごとの状態 enum。

接続が壁・扉・開口・障壁のどれであるかを表す `PassageKindEnum` と、
各形態が取りうる状態の enum を定義する。状態は文字列値として
`Passage` 値オブジェクトに保持される。
"""

from __future__ import annotations

from enum import Enum


class PassageKindEnum(Enum):
    """スポット間接続の通過形態。"""

    OPEN = "OPEN"
    """開口部（廊下・出入口など）。常に通行可。"""

    WALL = "WALL"
    """壁。基本通行不可だが、叩く・崩すなどで状態遷移しうる。"""

    DOOR = "DOOR"
    """扉。施錠・閉・開の状態を持つ。"""

    BARRIER = "BARRIER"
    """魔法結界・崖など、壁とも扉とも違う通行阻害。"""


class WallStateEnum(Enum):
    """壁の状態。"""

    INTACT = "INTACT"
    """無傷。通行不可、音は弱く漏れる。"""

    CRACKED = "CRACKED"
    """ヒビ入り。通行不可、音は中程度に漏れる。"""

    BROKEN = "BROKEN"
    """破壊済。通行可、音はほぼ自由に通る。"""


class DoorStateEnum(Enum):
    """扉の状態。"""

    LOCKED = "LOCKED"
    """施錠中。通行不可。"""

    CLOSED = "CLOSED"
    """閉。通行可（扉を開ける動作付き）。"""

    OPEN = "OPEN"
    """開きっぱなし。通行可、音もよく通る。"""


class BarrierStateEnum(Enum):
    """障壁（崖・結界等）の状態。"""

    ACTIVE = "ACTIVE"
    """有効。通行不可。"""

    INACTIVE = "INACTIVE"
    """無効化済。通行可。"""


class OpenStateEnum(Enum):
    """OPEN 形態の状態（実質固定）。"""

    OPEN = "OPEN"

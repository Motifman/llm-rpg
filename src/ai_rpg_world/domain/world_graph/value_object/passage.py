"""スポット接続の通過形態を表す値オブジェクト。

`Passage` は接続の構造的な状態（壁・扉・開口など）と現在の状態文字列
（壁なら INTACT/CRACKED/BROKEN 等）を保持し、そこから派生して
「通行可否」と「音透過率」を表現する。

`SpotConnection.is_passable` / `sound_permeability` の値はこの
`Passage` から導出される（`SpotConnection` 側でフィールド同期）。
シナリオ側は `passage` ブロックを宣言することで、レバー一つない壁
・施錠扉・崖などを統一的に表現できる。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple, Type

from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    BarrierStateEnum,
    DoorStateEnum,
    OpenStateEnum,
    PassageKindEnum,
    WallStateEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PassageValidationException,
)


_STATE_ENUM_BY_KIND: Dict[PassageKindEnum, Type[Enum]] = {
    PassageKindEnum.OPEN: OpenStateEnum,
    PassageKindEnum.WALL: WallStateEnum,
    PassageKindEnum.DOOR: DoorStateEnum,
    PassageKindEnum.BARRIER: BarrierStateEnum,
}


# (kind, state) -> (default_traversable, default_sound_permeability)
#
# DOOR.CLOSED は traversable=False とする。閉じた扉を通り抜けるには
# まず interaction で OPEN に遷移させる、という escape-room 系シナリオの
# 直感に合わせるため。古典 RPG 風に「閉でも素通り可」にしたい場合は
# シナリオ側で `traversable: true` の override を指定すればよい。
_DEFAULT_TABLE: Dict[Tuple[PassageKindEnum, str], Tuple[bool, float]] = {
    (PassageKindEnum.OPEN, OpenStateEnum.OPEN.value): (True, 1.0),

    (PassageKindEnum.WALL, WallStateEnum.INTACT.value): (False, 0.1),
    (PassageKindEnum.WALL, WallStateEnum.CRACKED.value): (False, 0.4),
    (PassageKindEnum.WALL, WallStateEnum.BROKEN.value): (True, 1.0),

    (PassageKindEnum.DOOR, DoorStateEnum.LOCKED.value): (False, 0.5),
    (PassageKindEnum.DOOR, DoorStateEnum.CLOSED.value): (False, 0.6),
    (PassageKindEnum.DOOR, DoorStateEnum.OPEN.value): (True, 1.0),

    (PassageKindEnum.BARRIER, BarrierStateEnum.ACTIVE.value): (False, 1.0),
    (PassageKindEnum.BARRIER, BarrierStateEnum.INACTIVE.value): (True, 1.0),
}


def _validate_state_for_kind(kind: PassageKindEnum, state: str) -> None:
    enum_cls = _STATE_ENUM_BY_KIND.get(kind)
    if enum_cls is None:
        raise PassageValidationException(f"Unknown passage kind: {kind}")
    valid = {m.value for m in enum_cls}
    if state not in valid:
        raise PassageValidationException(
            f"Invalid state '{state}' for passage kind {kind.value}. "
            f"Allowed: {sorted(valid)}"
        )


def _default_for(kind: PassageKindEnum, state: str) -> Tuple[bool, float]:
    key = (kind, state)
    if key not in _DEFAULT_TABLE:
        raise PassageValidationException(
            f"No default values registered for ({kind.value}, {state})"
        )
    return _DEFAULT_TABLE[key]


@dataclass(frozen=True)
class Passage:
    """スポット接続の通過形態と、現在の通行可否・音透過率。

    Attributes:
        kind: 通過形態（OPEN/WALL/DOOR/BARRIER）。
        state: 通過形態ごとの状態文字列（WALL なら "INTACT" 等）。
        traversable: 現在通行可能か。
        sound_permeability: 音透過率 [0.0, 1.0]。
    """

    kind: PassageKindEnum
    state: str
    traversable: bool
    sound_permeability: float

    def __post_init__(self) -> None:
        _validate_state_for_kind(self.kind, self.state)
        if not 0.0 <= self.sound_permeability <= 1.0:
            raise PassageValidationException(
                f"sound_permeability must be in [0.0, 1.0]: {self.sound_permeability}"
            )

    # ---- factories ---------------------------------------------------

    @classmethod
    def open(
        cls,
        *,
        traversable: Optional[bool] = None,
        sound_permeability: Optional[float] = None,
    ) -> "Passage":
        """開口部（既定で常に通行可）を生成する。

        OPEN は意味的に「常に通行可」を表すため、`traversable=False` を指定する
        ような使い方は避け、通行不可にしたい場合は `BARRIER` または `WALL` を
        使うこと。ただし完全に弾くと既存の override パターンと矛盾するため、
        引数自体は受け取り、警告ではなくシナリオ側責任とする。
        """
        default_t, default_s = _default_for(PassageKindEnum.OPEN, OpenStateEnum.OPEN.value)
        return cls(
            kind=PassageKindEnum.OPEN,
            state=OpenStateEnum.OPEN.value,
            traversable=default_t if traversable is None else traversable,
            sound_permeability=default_s if sound_permeability is None else sound_permeability,
        )

    @classmethod
    def wall(
        cls,
        state: WallStateEnum = WallStateEnum.INTACT,
        *,
        traversable: Optional[bool] = None,
        sound_permeability: Optional[float] = None,
    ) -> "Passage":
        """壁を生成する。state ごとのデフォルトは
        INTACT=通行不可/音0.1, CRACKED=通行不可/音0.4, BROKEN=通行可/音1.0。
        """
        default_t, default_s = _default_for(PassageKindEnum.WALL, state.value)
        return cls(
            kind=PassageKindEnum.WALL,
            state=state.value,
            traversable=default_t if traversable is None else traversable,
            sound_permeability=default_s if sound_permeability is None else sound_permeability,
        )

    @classmethod
    def door(
        cls,
        state: DoorStateEnum = DoorStateEnum.CLOSED,
        *,
        traversable: Optional[bool] = None,
        sound_permeability: Optional[float] = None,
    ) -> "Passage":
        """扉を生成する。state は LOCKED/CLOSED/OPEN。"""
        default_t, default_s = _default_for(PassageKindEnum.DOOR, state.value)
        return cls(
            kind=PassageKindEnum.DOOR,
            state=state.value,
            traversable=default_t if traversable is None else traversable,
            sound_permeability=default_s if sound_permeability is None else sound_permeability,
        )

    @classmethod
    def barrier(
        cls,
        state: BarrierStateEnum = BarrierStateEnum.ACTIVE,
        *,
        traversable: Optional[bool] = None,
        sound_permeability: Optional[float] = None,
    ) -> "Passage":
        """障壁（崖・結界等）を生成する。"""
        default_t, default_s = _default_for(PassageKindEnum.BARRIER, state.value)
        return cls(
            kind=PassageKindEnum.BARRIER,
            state=state.value,
            traversable=default_t if traversable is None else traversable,
            sound_permeability=default_s if sound_permeability is None else sound_permeability,
        )

    # ---- transitions -------------------------------------------------

    def with_state(
        self,
        new_state: str,
        *,
        traversable: Optional[bool] = None,
        sound_permeability: Optional[float] = None,
    ) -> "Passage":
        """同じ kind を維持したまま状態遷移した新しい Passage を返す。

        引数の override がない場合は kind+new_state のデフォルト値を使う。
        """
        _validate_state_for_kind(self.kind, new_state)
        default_t, default_s = _default_for(self.kind, new_state)
        return Passage(
            kind=self.kind,
            state=new_state,
            traversable=default_t if traversable is None else traversable,
            sound_permeability=default_s if sound_permeability is None else sound_permeability,
        )

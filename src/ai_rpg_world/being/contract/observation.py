"""環境がエージェントへ渡す観測。

欄の段は注釈の形で読める。

- 必須: ``T``。既定値が無い
- 分かるなら書く: ``T | Unknown``。既定値が無いので省けず、分からなければ ``UNKNOWN``
  を渡す。空と「不明」を区別するため、空文字は拒む
- 任意の助言: ``T | None = None``

経路ごとに必須の欄が変わるのは、経路を種類ごとの型にして表す。呼び出しの ID と
成否は「自分の行動の結果」の型だけが持つ。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, Union, get_args

from ai_rpg_world.being.contract.errors import (
    ContractViolation,
    require_bool,
    require_text,
)


class Unknown(Enum):
    UNKNOWN = "不明"


UNKNOWN: Final = Unknown.UNKNOWN
UnknownValue = Literal[Unknown.UNKNOWN]


@dataclass(frozen=True)
class SeenOrHeard:
    """見た・聞いた。"""


@dataclass(frozen=True)
class ToldOrWritten:
    """言われた・書かれていた。"""


@dataclass(frozen=True)
class OwnBodyState:
    """自分の体の状態。"""


@dataclass(frozen=True)
class OwnActionResult:
    """自分の行動の結果。

    呼び出しと 1 対 1 で必ず 1 件届く結果だけがこの経路になる。移動の到着や相手の
    返事のように後から届く結果は、呼び出しの ID を持たない他の経路で届く。
    """

    call_id: str
    succeeded: bool

    def __post_init__(self) -> None:
        require_text(self.call_id, "call_id")
        require_bool(self.succeeded, "succeeded")


@dataclass(frozen=True)
class EnvironmentNotice:
    """環境からの知らせ。"""


Route = Union[SeenOrHeard, ToldOrWritten, OwnBodyState, OwnActionResult, EnvironmentNotice]
_ROUTE_TYPES: Final = get_args(Route)


@dataclass(frozen=True)
class ObservedTime:
    """観測の時刻。

    ``seconds`` は同じ環境の中でだけ大小と差を比べられる。環境を跨いで比べない。
    """

    display: str
    seconds: float | None = None

    def __post_init__(self) -> None:
        require_text(self.display, "display")
        if self.seconds is None:
            return
        if (
            isinstance(self.seconds, bool)
            or not isinstance(self.seconds, (int, float))
            or not math.isfinite(self.seconds)
        ):
            raise ContractViolation("seconds must be a finite number or None")


KNOWN_IF_POSSIBLE_FIELDS: Final = ("subject_name", "source", "place", "addressed_to_self")


@dataclass(frozen=True, kw_only=True)
class Observation:
    """``wants_wake`` の None は助言なし、False は「起こさなくてよい」。

    ``body_if_subject_unknown`` は、主体を知らない受け手向けに名前を伏せた本文。
    どちらの本文で覚えるかは、受け手の Being が自分の知り合いの記録で決める。
    """

    body: str
    route: Route
    time: ObservedTime
    subject_is_self: bool

    subject_name: str | UnknownValue
    source: str | UnknownValue
    place: str | UnknownValue
    addressed_to_self: bool | UnknownValue

    wants_wake: bool | None = None
    body_if_subject_unknown: str | None = None

    def __post_init__(self) -> None:
        require_text(self.body, "body")
        if not isinstance(self.route, _ROUTE_TYPES):
            raise ContractViolation("route must be one of the five routes")
        if not isinstance(self.time, ObservedTime):
            raise ContractViolation("time must be ObservedTime")
        require_bool(self.subject_is_self, "subject_is_self")
        for name in ("subject_name", "source", "place"):
            value = getattr(self, name)
            if value is not UNKNOWN:
                require_text(value, name)
        if self.addressed_to_self is not UNKNOWN:
            require_bool(self.addressed_to_self, "addressed_to_self")
        if self.wants_wake is not None:
            require_bool(self.wants_wake, "wants_wake")
        if self.body_if_subject_unknown is not None:
            require_text(self.body_if_subject_unknown, "body_if_subject_unknown")
            if self.subject_name is UNKNOWN or self.subject_is_self:
                raise ContractViolation(
                    "body_if_subject_unknown needs a known subject other than self"
                )

    def unknown_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name in KNOWN_IF_POSSIBLE_FIELDS if getattr(self, name) is UNKNOWN
        )

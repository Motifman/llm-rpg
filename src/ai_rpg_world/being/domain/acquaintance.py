"""Being が会ったことのある相手の記録。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class AcquaintanceInvalid(ValueError):
    """知り合いの記録が決まりを満たさない。"""


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AcquaintanceInvalid(f"{field_name} must be non-blank str")


def _require_turn(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AcquaintanceInvalid(f"{field_name} must be int >= 0")


@dataclass(frozen=True, kw_only=True)
class Acquaintance:
    """相手は環境の名前と相手の名前の組で見分ける。

    同じ人でも環境ごとに名前が違い、別の環境の同じ名前は別の人でありうる。
    ターンは世界の時刻ではなく Being の記憶のターン数で、環境を跨いでも進み続ける。
    """

    environment_name: str
    name: str
    first_met_turn: int
    last_met_turn: int
    met_count: int

    def __post_init__(self) -> None:
        _require_text(self.environment_name, "environment_name")
        _require_text(self.name, "name")
        _require_turn(self.first_met_turn, "first_met_turn")
        _require_turn(self.last_met_turn, "last_met_turn")
        if self.last_met_turn < self.first_met_turn:
            raise AcquaintanceInvalid("last_met_turn must be >= first_met_turn")
        if (
            not isinstance(self.met_count, int)
            or isinstance(self.met_count, bool)
            or self.met_count < 1
        ):
            raise AcquaintanceInvalid("met_count must be int >= 1")

    @classmethod
    def first_meeting(
        cls, *, environment_name: str, name: str, turn: int
    ) -> Acquaintance:
        return cls(
            environment_name=environment_name,
            name=name,
            first_met_turn=turn,
            last_met_turn=turn,
            met_count=1,
        )

    def met_again(self, *, turn: int) -> Acquaintance:
        _require_turn(turn, "turn")
        if turn < self.last_met_turn:
            raise AcquaintanceInvalid("turn must not go back before last_met_turn")
        return Acquaintance(
            environment_name=self.environment_name,
            name=self.name,
            first_met_turn=self.first_met_turn,
            last_met_turn=turn,
            met_count=self.met_count + 1,
        )

    @property
    def is_first_meeting(self) -> bool:
        return self.met_count == 1


class AcquaintanceRepository(ABC):
    @abstractmethod
    def record_meeting(
        self, being_id: BeingId, *, environment_name: str, name: str, turn: int
    ) -> Acquaintance:
        """初めてなら記録を作り、会ったことがあれば会い直した記録に置き換えて返す。"""

    @abstractmethod
    def find(
        self, being_id: BeingId, *, environment_name: str, name: str
    ) -> Acquaintance | None: ...

    @abstractmethod
    def list_by_being(self, being_id: BeingId) -> tuple[Acquaintance, ...]:
        """初めて会った順に返す。"""

    @abstractmethod
    def replace_all_by_being(
        self, being_id: BeingId, acquaintances: Sequence[Acquaintance]
    ) -> None: ...


__all__ = ["Acquaintance", "AcquaintanceInvalid", "AcquaintanceRepository"]

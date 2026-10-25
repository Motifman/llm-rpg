"""Being が知っている相手の記録。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class AcquaintanceInvalid(ValueError):
    """知り合いの記録が決まりを満たさない。"""


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AcquaintanceInvalid(f"{field_name} must be non-blank str")


def _require_turn(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AcquaintanceInvalid(f"{field_name} must be int >= 0")


class HowKnown(Enum):
    """相手を初めて知った経路。あとで会っても変わらない。"""

    INTRODUCED = "紹介された"
    MET = "会った"


@dataclass(frozen=True, kw_only=True)
class Acquaintance:
    """相手は環境の名前と相手の名前の組で見分ける。

    同じ人でも環境ごとに名前が違い、別の環境の同じ名前は別の人でありうる。
    ターンは世界の時刻ではなく Being の記憶のターン数で、環境を跨いでも進み続ける。
    紹介されただけでまだ会っていない相手は、会った回数が 0 になる。
    名前を知らずに会った相手は ``name_learned_turn`` が None で、鍵の名前は
    プロンプトに出さない (#1581)。
    """

    environment_name: str
    name: str
    how_known: HowKnown
    known_since_turn: int
    name_learned_turn: int | None
    relation_note: str | None = None
    met_count: int = 0
    first_met_turn: int | None = None
    last_met_turn: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.environment_name, "environment_name")
        _require_text(self.name, "name")
        if not isinstance(self.how_known, HowKnown):
            raise AcquaintanceInvalid("how_known must be HowKnown")
        _require_turn(self.known_since_turn, "known_since_turn")
        if self.relation_note is not None:
            _require_text(self.relation_note, "relation_note")
        if not isinstance(self.met_count, int) or isinstance(self.met_count, bool) or self.met_count < 0:
            raise AcquaintanceInvalid("met_count must be int >= 0")
        if self.name_learned_turn is not None:
            _require_turn(self.name_learned_turn, "name_learned_turn")
        if self.how_known is HowKnown.INTRODUCED and self.name_learned_turn != self.known_since_turn:
            raise AcquaintanceInvalid("an introduction tells the name when introduced")
        if self.met_count == 0:
            if self.first_met_turn is not None or self.last_met_turn is not None:
                raise AcquaintanceInvalid("met turns must be None before meeting")
            if self.how_known is HowKnown.MET:
                raise AcquaintanceInvalid("known by meeting needs a meeting")
            return
        if self.first_met_turn is None or self.last_met_turn is None:
            raise AcquaintanceInvalid("met turns are required after meeting")
        _require_turn(self.first_met_turn, "first_met_turn")
        _require_turn(self.last_met_turn, "last_met_turn")
        if self.last_met_turn < self.first_met_turn:
            raise AcquaintanceInvalid("last_met_turn must be >= first_met_turn")
        if self.first_met_turn < self.known_since_turn:
            raise AcquaintanceInvalid("first_met_turn must be >= known_since_turn")
        if self.how_known is HowKnown.MET and self.first_met_turn != self.known_since_turn:
            raise AcquaintanceInvalid("known by meeting must be known at the first meeting")
        if (
            self.how_known is HowKnown.MET
            and self.name_learned_turn is not None
            and self.name_learned_turn < self.first_met_turn
        ):
            raise AcquaintanceInvalid("a name is learned only after meeting")

    @classmethod
    def first_meeting(cls, *, environment_name: str, name: str, turn: int, knows_name: bool = True) -> Acquaintance:
        return cls(
            environment_name=environment_name,
            name=name,
            how_known=HowKnown.MET,
            known_since_turn=turn,
            name_learned_turn=turn if knows_name else None,
            met_count=1,
            first_met_turn=turn,
            last_met_turn=turn,
        )

    @classmethod
    def introduced(
        cls,
        *,
        environment_name: str,
        name: str,
        turn: int,
        relation_note: str | None = None,
    ) -> Acquaintance:
        return cls(
            environment_name=environment_name,
            name=name,
            how_known=HowKnown.INTRODUCED,
            known_since_turn=turn,
            name_learned_turn=turn,
            relation_note=relation_note,
        )

    def met_at(self, *, turn: int) -> Acquaintance:
        _require_turn(turn, "turn")
        floor = self.last_met_turn if self.last_met_turn is not None else self.known_since_turn
        if turn < floor:
            raise AcquaintanceInvalid("turn must not go back before the last known turn")
        return replace(
            self,
            met_count=self.met_count + 1,
            first_met_turn=self.first_met_turn if self.first_met_turn is not None else turn,
            last_met_turn=turn,
        )

    def learned_name(self, *, turn: int) -> Acquaintance:
        """すでに名前を知っていれば、知ったターンは変えない。"""
        if self.name_learned_turn is not None:
            return self
        return replace(self, name_learned_turn=turn)

    @property
    def knows_name(self) -> bool:
        return self.name_learned_turn is not None

    @property
    def is_first_meeting(self) -> bool:
        return self.met_count == 1


class AcquaintanceRepository(ABC):
    @abstractmethod
    def record_meeting(
        self,
        being_id: BeingId,
        *,
        environment_name: str,
        name: str,
        turn: int,
        knows_name: bool = True,
    ) -> Acquaintance:
        """知らない相手なら会って知った記録を作り、知っている相手なら会った記録に置き換えて返す。

        ``knows_name`` は新しく作る記録にだけ効く。名前を知った記録は、会い直しても忘れない。
        """

    @abstractmethod
    def record_name_learned(
        self, being_id: BeingId, *, environment_name: str, name: str, turn: int
    ) -> Acquaintance | None:
        """会ったことのある相手の名前を知った記録にして返す。会ったことが無ければ何も記録せず None を返す。"""

    @abstractmethod
    def record_introduction(
        self,
        being_id: BeingId,
        *,
        environment_name: str,
        name: str,
        turn: int,
        relation_note: str | None,
    ) -> Acquaintance:
        """知らない相手なら紹介された記録を作る。すでに知っている相手は、名前を知らなければ名前を知った記録にして返し、ほかは変えない。"""

    @abstractmethod
    def find(self, being_id: BeingId, *, environment_name: str, name: str) -> Acquaintance | None: ...

    @abstractmethod
    def list_by_being(self, being_id: BeingId) -> tuple[Acquaintance, ...]:
        """知った順に返す。"""

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, acquaintances: Sequence[Acquaintance]) -> None: ...


__all__ = ["Acquaintance", "AcquaintanceInvalid", "AcquaintanceRepository", "HowKnown"]

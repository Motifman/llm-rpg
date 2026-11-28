"""Being が知っている相手の名簿と、その中の 1 人ぶんの記録。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import (
    AcquaintanceDuplicatedException,
    AcquaintanceValidationException,
)
from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AcquaintanceValidationException(f"{field_name} must be non-blank str")


def _require_turn(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AcquaintanceValidationException(f"{field_name} must be int >= 0")


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
            raise AcquaintanceValidationException("how_known must be HowKnown")
        _require_turn(self.known_since_turn, "known_since_turn")
        if self.relation_note is not None:
            _require_text(self.relation_note, "relation_note")
        if not isinstance(self.met_count, int) or isinstance(self.met_count, bool) or self.met_count < 0:
            raise AcquaintanceValidationException("met_count must be int >= 0")
        if self.name_learned_turn is not None:
            _require_turn(self.name_learned_turn, "name_learned_turn")
        if self.how_known is HowKnown.INTRODUCED and self.name_learned_turn != self.known_since_turn:
            raise AcquaintanceValidationException("an introduction tells the name when introduced")
        if self.met_count == 0:
            if self.first_met_turn is not None or self.last_met_turn is not None:
                raise AcquaintanceValidationException("met turns must be None before meeting")
            if self.how_known is HowKnown.MET:
                raise AcquaintanceValidationException("known by meeting needs a meeting")
            return
        if self.first_met_turn is None or self.last_met_turn is None:
            raise AcquaintanceValidationException("met turns are required after meeting")
        _require_turn(self.first_met_turn, "first_met_turn")
        _require_turn(self.last_met_turn, "last_met_turn")
        if self.last_met_turn < self.first_met_turn:
            raise AcquaintanceValidationException("last_met_turn must be >= first_met_turn")
        if self.first_met_turn < self.known_since_turn:
            raise AcquaintanceValidationException("first_met_turn must be >= known_since_turn")
        if self.how_known is HowKnown.MET and self.first_met_turn != self.known_since_turn:
            raise AcquaintanceValidationException("known by meeting must be known at the first meeting")
        if (
            self.how_known is HowKnown.MET
            and self.name_learned_turn is not None
            and self.name_learned_turn < self.first_met_turn
        ):
            raise AcquaintanceValidationException("a name is learned only after meeting")

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
            raise AcquaintanceValidationException("turn must not go back before the last known turn")
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


@dataclass(frozen=True, kw_only=True)
class AcquaintanceIntroducedEvent(DomainEvent):
    being_id: BeingId
    acquaintance: Acquaintance


@dataclass(frozen=True, kw_only=True)
class AcquaintanceMetEvent(DomainEvent):
    """``acquaintance`` は会ったあとの記録。"""

    being_id: BeingId
    acquaintance: Acquaintance


@dataclass(frozen=True, kw_only=True)
class AcquaintanceNameLearnedEvent(DomainEvent):
    """``acquaintance`` は名前を知ったあとの記録。"""

    being_id: BeingId
    acquaintance: Acquaintance


AcquaintanceRosterEvent = AcquaintanceIntroducedEvent | AcquaintanceMetEvent | AcquaintanceNameLearnedEvent

_Key = tuple[str, str]


def _key(acquaintance: Acquaintance) -> _Key:
    return (acquaintance.environment_name, acquaintance.name)


def _checked(acquaintances: object) -> tuple[Acquaintance, ...]:
    if not isinstance(acquaintances, tuple) or not all(isinstance(a, Acquaintance) for a in acquaintances):
        raise AcquaintanceValidationException("acquaintances must be a tuple of Acquaintance")
    keys = [_key(a) for a in acquaintances]
    duplicated = sorted({k for k in keys if keys.count(k) > 1})
    if duplicated:
        raise AcquaintanceDuplicatedException(f"duplicate acquaintance: {duplicated}")
    return acquaintances


class AcquaintanceRoster(AggregateRoot[AcquaintanceRosterEvent]):
    """Being ごとに 1 つある、知っている相手の名簿。並びは知った順。

    操作は中身を書き換え、値を返さない。記録が変わったときだけイベントをためる。
    決まりに反する操作は例外を投げ、中身もためたイベントも変えない。
    """

    def __init__(self, being_id: BeingId, *, acquaintances: tuple[Acquaintance, ...] = ()) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise AcquaintanceValidationException("being_id must be BeingId")
        self._being_id = being_id
        self._acquaintances = _checked(acquaintances)

    @classmethod
    def empty(cls, being_id: BeingId) -> AcquaintanceRoster:
        return cls(being_id)

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def acquaintances(self) -> tuple[Acquaintance, ...]:
        return self._acquaintances

    def find(self, *, environment_name: str, name: str) -> Acquaintance | None:
        for acquaintance in self._acquaintances:
            if _key(acquaintance) == (environment_name, name):
                return acquaintance
        return None

    def introduce(self, *, environment_name: str, name: str, turn: int, relation_note: str | None) -> None:
        """知っている相手は、名前を知らなければ名前を覚えるだけにする。

        関係の注記は紹介でだけ付く決まり (D1520) だが、会ったあとの紹介では付けない。
        """
        known = self.find(environment_name=environment_name, name=name)
        if known is not None:
            self.learn_name(environment_name=environment_name, name=name, turn=turn)
            return
        introduced = Acquaintance.introduced(
            environment_name=environment_name, name=name, turn=turn, relation_note=relation_note
        )
        self._acquaintances = (*self._acquaintances, introduced)
        self.add_event(
            AcquaintanceIntroducedEvent(**new_event_stamp(), being_id=self._being_id, acquaintance=introduced)
        )

    def meet(self, *, environment_name: str, name: str, turn: int, knows_name: bool = True) -> None:
        """``knows_name`` は知らない相手にだけ効く。名前を知った記録は、会い直しても忘れない。"""
        known = self.find(environment_name=environment_name, name=name)
        if known is None:
            met = Acquaintance.first_meeting(
                environment_name=environment_name, name=name, turn=turn, knows_name=knows_name
            )
            self._acquaintances = (*self._acquaintances, met)
        else:
            met = known.met_at(turn=turn)
            self._replace(known, met)
        self.add_event(AcquaintanceMetEvent(**new_event_stamp(), being_id=self._being_id, acquaintance=met))

    def learn_name(self, *, environment_name: str, name: str, turn: int) -> None:
        """知らない相手や、すでに名前を知っている相手なら何も変えない。"""
        known = self.find(environment_name=environment_name, name=name)
        if known is None or known.knows_name:
            return
        named = known.learned_name(turn=turn)
        self._replace(known, named)
        self.add_event(AcquaintanceNameLearnedEvent(**new_event_stamp(), being_id=self._being_id, acquaintance=named))

    def _replace(self, before: Acquaintance, after: Acquaintance) -> None:
        self._acquaintances = tuple(after if a is before else a for a in self._acquaintances)


class AcquaintanceRepository(ABC):
    @abstractmethod
    def get(self, being_id: BeingId) -> AcquaintanceRoster:
        """まだ誰も知らない Being には空の名簿を返す。返した集約を書き換えても、``save`` するまで保存先は変わらない。"""

    @abstractmethod
    def save(self, roster: AcquaintanceRoster) -> None:
        """保存したあとで渡した集約を書き換えても、保存先は変わらない。ためたイベントは取り出して配り手に渡す。"""

    @abstractmethod
    def replace_all_by_being(self, roster: AcquaintanceRoster) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。"""


__all__ = [
    "Acquaintance",
    "AcquaintanceIntroducedEvent",
    "AcquaintanceMetEvent",
    "AcquaintanceNameLearnedEvent",
    "AcquaintanceRepository",
    "AcquaintanceRoster",
    "AcquaintanceRosterEvent",
    "HowKnown",
]

"""Being が書くメモ帳と、その中のメモ。"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import (
    MemoLimitReachedException,
    MemoNotFoundException,
    MemoValidationException,
)
from ai_rpg_world.eventing import AggregateRoot, DomainEvent

MEMO_TEXT_MAX_LENGTH = 60
HANDLE_PREFIX = "m_"
HANDLE_MIN_ID_LENGTH = 6
EPISODE_HANDLE_PREFIX = "ep_"


class MemoKind(Enum):
    TODO = "todo"
    FACT = "fact"
    PERSON = "person"


class MemoSource(Enum):
    SELF = "self"
    HEARD = "heard"
    EPISODE = "episode"


class MemoCertainty(Enum):
    SURE = "sure"
    GUESS = "guess"


#: 上限はプロンプトの大きさの都合で、意味の区切りではない。
KIND_LIMITS: Mapping[MemoKind, int] = MappingProxyType({MemoKind.TODO: 5, MemoKind.FACT: 10, MemoKind.PERSON: 5})


def _require_text(value: object, field_name: str, *, max_length: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MemoValidationException(f"{field_name} must be non-blank str")
    if max_length is not None and len(value) > max_length:
        raise MemoValidationException(f"{field_name} must be at most {max_length} characters, got {len(value)}")


def _require_turn(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MemoValidationException(f"{field_name} must be int >= 0")


def _id_hex(memo_id: object) -> str:
    if not isinstance(memo_id, str):
        raise MemoValidationException("memo_id must be str")
    try:
        parsed = uuid.UUID(memo_id)
    except ValueError as exc:
        raise MemoValidationException(f"memo_id must be a UUID: {memo_id!r}") from exc
    if str(parsed) != memo_id:
        raise MemoValidationException(f"memo_id must be a lowercase hyphenated UUID: {memo_id!r}")
    return parsed.hex


def _handle_for(memo_id: str, taken_handles: Collection[str]) -> str:
    """エピソードの呼び名と同じく、重なったら後から足した側だけを伸ばす (design_decisions D1623)。"""
    hex_id = _id_hex(memo_id)
    for length in range(HANDLE_MIN_ID_LENGTH, len(hex_id) + 1):
        handle = f"{HANDLE_PREFIX}{hex_id[:length]}"
        if handle not in taken_handles:
            return handle
    raise MemoValidationException(f"every handle of {memo_id!r} is taken")


@dataclass(frozen=True)
class MemoProvenance:
    """分かったことの出どころと確かさ。

    2 つを分けるのは、人から聞いた推測と自分の推測を区別するため。
    ``source_from`` は、人から聞いたなら誰から、エピソードからならその呼び名。
    """

    source: MemoSource
    certainty: MemoCertainty
    source_from: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, MemoSource):
            raise MemoValidationException("source must be MemoSource")
        if not isinstance(self.certainty, MemoCertainty):
            raise MemoValidationException("certainty must be MemoCertainty")
        if self.source is MemoSource.SELF:
            if self.source_from is not None:
                raise MemoValidationException("source_from must be None when source is self")
            return
        _require_text(self.source_from, "source_from")
        if self.source is MemoSource.EPISODE and not str(self.source_from).startswith(EPISODE_HANDLE_PREFIX):
            raise MemoValidationException(f"source_from must be an episode handle, got {self.source_from!r}")


@dataclass(frozen=True, kw_only=True)
class Memo:
    """ターンは Being の記憶のターン数。ゲームの番号は持たない。"""

    memo_id: str
    handle: str
    kind: MemoKind
    text: str
    provenance: MemoProvenance | None
    written_turn: int
    edited_turn: int | None = None
    environment_name: str

    def __post_init__(self) -> None:
        hex_id = _id_hex(self.memo_id)
        if not isinstance(self.handle, str):
            raise MemoValidationException("handle must be str")
        id_part = self.handle.removeprefix(HANDLE_PREFIX)
        if (
            not self.handle.startswith(HANDLE_PREFIX)
            or len(id_part) < HANDLE_MIN_ID_LENGTH
            or not hex_id.startswith(id_part)
        ):
            raise MemoValidationException(f"handle {self.handle!r} does not come from memo_id {self.memo_id!r}")
        if not isinstance(self.kind, MemoKind):
            raise MemoValidationException("kind must be MemoKind")
        _require_text(self.text, "text", max_length=MEMO_TEXT_MAX_LENGTH)
        if self.kind is MemoKind.FACT:
            if not isinstance(self.provenance, MemoProvenance):
                raise MemoValidationException("a fact memo needs provenance")
        elif self.provenance is not None:
            raise MemoValidationException(f"a {self.kind.value} memo must not have provenance")
        _require_turn(self.written_turn, "written_turn")
        if self.edited_turn is not None:
            _require_turn(self.edited_turn, "edited_turn")
            if self.edited_turn < self.written_turn:
                raise MemoValidationException("edited_turn must be >= written_turn")
        _require_text(self.environment_name, "environment_name")


def _require_known_episode(provenance: MemoProvenance | None, known_episode_handles: Collection[str]) -> None:
    if (
        provenance is not None
        and provenance.source is MemoSource.EPISODE
        and provenance.source_from not in known_episode_handles
    ):
        raise MemoValidationException(f"no episode {provenance.source_from!r}")


@dataclass(frozen=True, kw_only=True)
class MemoAdded(DomainEvent):
    being_id: BeingId
    memo: Memo


@dataclass(frozen=True, kw_only=True)
class MemoEdited(DomainEvent):
    """``memo`` は書き換えたあとのメモ。"""

    being_id: BeingId
    memo: Memo


@dataclass(frozen=True, kw_only=True)
class MemoRemoved(DomainEvent):
    being_id: BeingId
    memo: Memo


MemoBookEvent = MemoAdded | MemoEdited | MemoRemoved


def _checked(memos: object) -> tuple[Memo, ...]:
    if not isinstance(memos, tuple) or not all(isinstance(m, Memo) for m in memos):
        raise MemoValidationException("memos must be a tuple of Memo")
    for field_name in ("memo_id", "handle"):
        values = [getattr(m, field_name) for m in memos]
        if len(set(values)) != len(values):
            raise MemoValidationException(f"the same {field_name} appears twice")
    for kind, limit in KIND_LIMITS.items():
        if sum(1 for m in memos if m.kind is kind) > limit:
            raise MemoValidationException(f"more than {limit} {kind.value} memos")
    return memos


class MemoBook(AggregateRoot[MemoBookEvent]):
    """Being ごとに 1 つある、メモを持つ集約。分類ごとの件数の上限は、複数のメモにまたがる決まりなのでここで守る。

    並びは書いた順。操作は中身を書き換え、値を返さない。足した・書き換えた・消したメモは
    イベントとしてためる。決まりに反する操作は例外を投げ、中身もためたイベントも変えない。
    """

    def __init__(self, being_id: BeingId, *, memos: tuple[Memo, ...] = ()) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise MemoValidationException("being_id must be BeingId")
        self._being_id = being_id
        self._memos = _checked(memos)

    @classmethod
    def empty(cls, being_id: BeingId) -> MemoBook:
        return cls(being_id)

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def memos(self) -> tuple[Memo, ...]:
        return self._memos

    def _count(self, kind: MemoKind) -> int:
        return sum(1 for m in self._memos if m.kind is kind)

    def find(self, handle: str) -> Memo | None:
        for memo in self._memos:
            if memo.handle == handle:
                return memo
        return None

    def _require(self, handle: str) -> Memo:
        memo = self.find(handle)
        if memo is None:
            raise MemoNotFoundException(f"no memo {handle!r}")
        return memo

    def add(
        self,
        *,
        memo_id: str,
        kind: MemoKind,
        text: str,
        provenance: MemoProvenance | None,
        turn: int,
        environment_name: str,
        known_episode_handles: Collection[str] = (),
    ) -> None:
        """``known_episode_handles`` は、出どころに書けるエピソードの呼び名。"""
        if isinstance(kind, MemoKind) and self._count(kind) >= KIND_LIMITS[kind]:
            raise MemoLimitReachedException(f"{kind.value} memos are at the limit of {KIND_LIMITS[kind]}")
        _require_known_episode(provenance, known_episode_handles)
        memo = Memo(
            memo_id=memo_id,
            handle=_handle_for(memo_id, {m.handle for m in self._memos}),
            kind=kind,
            text=text,
            provenance=provenance,
            written_turn=turn,
            environment_name=environment_name,
        )
        self._memos = _checked((*self._memos, memo))
        self.add_event(
            MemoAdded(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                memo=memo,
            )
        )

    def edit(
        self,
        handle: str,
        *,
        text: str,
        turn: int,
        provenance: MemoProvenance | None = None,
        known_episode_handles: Collection[str] = (),
    ) -> None:
        """``provenance`` を渡さなければ、分かったことでも前の出どころのまま。"""
        memo = self._require(handle)
        _require_known_episode(provenance, known_episode_handles)
        _require_turn(turn, "turn")
        if memo.edited_turn is not None and turn < memo.edited_turn:
            raise MemoValidationException("turn must not go back before the last edit")
        edited = replace(
            memo,
            text=text,
            provenance=provenance if provenance is not None else memo.provenance,
            edited_turn=turn,
        )
        self._memos = _checked(tuple(edited if m is memo else m for m in self._memos))
        self.add_event(
            MemoEdited(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                memo=edited,
            )
        )

    def remove(self, handle: str) -> None:
        memo = self._require(handle)
        self._memos = tuple(m for m in self._memos if m is not memo)
        self.add_event(
            MemoRemoved(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                memo=memo,
            )
        )


class MemoBookRepository(ABC):
    @abstractmethod
    def get(self, being_id: BeingId) -> MemoBook:
        """まだ何も書いていない Being には空のメモ帳を返す。返した集約を書き換えても、``save`` するまで保存先は変わらない。"""

    @abstractmethod
    def save(self, book: MemoBook) -> None:
        """保存したあとで渡した集約を書き換えても、保存先は変わらない。ためたイベントは取り出して配り手に渡す。"""

    @abstractmethod
    def replace_all_by_being(self, book: MemoBook) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。"""


__all__ = [
    "KIND_LIMITS",
    "MEMO_TEXT_MAX_LENGTH",
    "Memo",
    "MemoAdded",
    "MemoBook",
    "MemoBookEvent",
    "MemoBookRepository",
    "MemoCertainty",
    "MemoEdited",
    "MemoKind",
    "MemoProvenance",
    "MemoRemoved",
    "MemoSource",
]

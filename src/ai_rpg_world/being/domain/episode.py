"""Being が書いた、目次つきのエピソード。"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AggregateRoot, DomainEvent

INDEX_TEXT_MAX_LENGTH = 40
BODY_MAX_LENGTH = 400
HANDLE_PREFIX = "ep_"
HANDLE_MIN_ID_LENGTH = 6


def _require_text(value: object, field_name: str, *, max_length: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EpisodeValidationException(f"{field_name} must be non-blank str")
    if max_length is not None and len(value) > max_length:
        raise EpisodeValidationException(f"{field_name} must be at most {max_length} characters, got {len(value)}")


def _require_turn(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EpisodeValidationException(f"{field_name} must be int >= 0")


def _id_hex(episode_id: object) -> str:
    if not isinstance(episode_id, str):
        raise EpisodeValidationException("episode_id must be str")
    try:
        parsed = uuid.UUID(episode_id)
    except ValueError as exc:
        raise EpisodeValidationException(f"episode_id must be a UUID: {episode_id!r}") from exc
    if str(parsed) != episode_id:
        raise EpisodeValidationException(f"episode_id must be a lowercase hyphenated UUID: {episode_id!r}")
    return parsed.hex


def _handle_for(episode_id: str, taken_handles: Collection[str]) -> str:
    """呼び名は ID の区切りを除いた先頭から作り、重なったら 1 文字ずつ伸ばす。

    前からある呼び名は変えない。プロンプトの履歴に残った呼び名が指す先をずらさないため。
    """
    hex_id = _id_hex(episode_id)
    for length in range(HANDLE_MIN_ID_LENGTH, len(hex_id) + 1):
        handle = f"{HANDLE_PREFIX}{hex_id[:length]}"
        if handle not in taken_handles:
            return handle
    raise EpisodeValidationException(f"every handle of {episode_id!r} is taken")


@dataclass(frozen=True)
class EpisodeIndex:
    """目次。本人がこれを見て、本文を呼び出すかを決める。"""

    summary: str
    recall_when: str

    def __post_init__(self) -> None:
        _require_text(self.summary, "summary", max_length=INDEX_TEXT_MAX_LENGTH)
        _require_text(self.recall_when, "recall_when", max_length=INDEX_TEXT_MAX_LENGTH)


@dataclass(frozen=True)
class IndexRevision:
    """直す前の目次と、直したターン。"""

    previous: EpisodeIndex
    revised_turn: int

    def __post_init__(self) -> None:
        if not isinstance(self.previous, EpisodeIndex):
            raise EpisodeValidationException("previous must be EpisodeIndex")
        _require_turn(self.revised_turn, "revised_turn")


@dataclass(frozen=True, kw_only=True)
class EpisodeRecalled(DomainEvent):
    """``recall_count`` は呼び出したあとの回数。"""

    being_id: BeingId
    episode_id: str
    handle: str
    turn: int
    recall_count: int


@dataclass(frozen=True, kw_only=True)
class EpisodeIndexRevised(DomainEvent):
    being_id: BeingId
    episode_id: str
    handle: str
    previous: EpisodeIndex
    index: EpisodeIndex
    turn: int


@dataclass(frozen=True, kw_only=True)
class EpisodeWrittenEvent(DomainEvent):
    """本人がエピソードを書き起こし、記憶に加えた。"""

    being_id: BeingId
    episode_id: str
    handle: str
    environment_name: str
    written_turn: int
    index: EpisodeIndex
    body: str


EpisodeEvent = EpisodeRecalled | EpisodeIndexRevised | EpisodeWrittenEvent


def _require_recalls(recall_count: object, last_recalled_turn: object, written_turn: int) -> None:
    if not isinstance(recall_count, int) or isinstance(recall_count, bool) or recall_count < 0:
        raise EpisodeValidationException("recall_count must be int >= 0")
    if recall_count == 0:
        if last_recalled_turn is not None:
            raise EpisodeValidationException("last_recalled_turn must be None before any recall")
        return
    if last_recalled_turn is None:
        raise EpisodeValidationException("last_recalled_turn is required after a recall")
    _require_turn(last_recalled_turn, "last_recalled_turn")
    assert isinstance(last_recalled_turn, int)
    if last_recalled_turn < written_turn:
        raise EpisodeValidationException("last_recalled_turn must be >= written_turn")


def _require_history(index: object, index_history: object, written_turn: int) -> None:
    if not isinstance(index, EpisodeIndex):
        raise EpisodeValidationException("index must be EpisodeIndex")
    if not isinstance(index_history, tuple):
        raise EpisodeValidationException("index_history must be tuple")
    floor = written_turn
    for revision in index_history:
        if not isinstance(revision, IndexRevision):
            raise EpisodeValidationException("index_history must hold IndexRevision")
        if revision.revised_turn < floor:
            raise EpisodeValidationException("index_history must be ordered by revised_turn from written_turn")
        floor = revision.revised_turn


class Episode(AggregateRoot[EpisodeEvent]):
    """1 件ずつ ID を持つ、目次つきのエピソードの集約。書いた Being の ID と、目次も持つ (design_decisions D1621)。

    ターンは世界の時刻ではなく Being の記憶のターン数で、環境を跨いでも進み続ける。
    呼び出しと目次の直しは中身を書き換え、値を返さず、イベントとしてためる。決まりに反する
    操作は例外を投げ、中身もためたイベントも変えない。本文・呼び名・書いた時は変わらない。
    """

    def __init__(
        self,
        *,
        being_id: BeingId,
        episode_id: str,
        handle: str,
        environment_name: str,
        written_turn: int,
        index: EpisodeIndex,
        body: str,
        recall_count: int = 0,
        last_recalled_turn: int | None = None,
        index_history: tuple[IndexRevision, ...] = (),
    ) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise EpisodeValidationException("being_id must be BeingId")
        hex_id = _id_hex(episode_id)
        if not isinstance(handle, str):
            raise EpisodeValidationException("handle must be str")
        id_part = handle.removeprefix(HANDLE_PREFIX)
        if (
            not handle.startswith(HANDLE_PREFIX)
            or len(id_part) < HANDLE_MIN_ID_LENGTH
            or not hex_id.startswith(id_part)
        ):
            raise EpisodeValidationException(f"handle {handle!r} does not come from episode_id {episode_id!r}")
        _require_text(environment_name, "environment_name")
        _require_turn(written_turn, "written_turn")
        _require_text(body, "body", max_length=BODY_MAX_LENGTH)
        _require_recalls(recall_count, last_recalled_turn, written_turn)
        _require_history(index, index_history, written_turn)
        self._being_id = being_id
        self._episode_id = episode_id
        self._handle = handle
        self._environment_name = environment_name
        self._written_turn = written_turn
        self._body = body
        self._recall_count = recall_count
        self._last_recalled_turn = last_recalled_turn
        self._index = index
        self._index_history = index_history

    @classmethod
    def write(
        cls,
        *,
        being_id: BeingId,
        episode_id: str,
        environment_name: str,
        written_turn: int,
        index: EpisodeIndex,
        body: str,
        taken_handles: Collection[str] = (),
    ) -> Episode:
        """``taken_handles`` は同じ Being がもう使っている呼び名。書いたことを ``EpisodeWrittenEvent`` としてためる。"""
        episode = cls(
            being_id=being_id,
            episode_id=episode_id,
            handle=_handle_for(episode_id, taken_handles),
            environment_name=environment_name,
            written_turn=written_turn,
            index=index,
            body=body,
        )
        episode.add_event(
            EpisodeWrittenEvent(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=being_id,
                episode_id=episode_id,
                handle=episode.handle,
                environment_name=environment_name,
                written_turn=written_turn,
                index=index,
                body=body,
            )
        )
        return episode

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def episode_id(self) -> str:
        return self._episode_id

    @property
    def handle(self) -> str:
        return self._handle

    @property
    def environment_name(self) -> str:
        return self._environment_name

    @property
    def written_turn(self) -> int:
        return self._written_turn

    @property
    def index(self) -> EpisodeIndex:
        return self._index

    @property
    def body(self) -> str:
        return self._body

    @property
    def recall_count(self) -> int:
        return self._recall_count

    @property
    def last_recalled_turn(self) -> int | None:
        return self._last_recalled_turn

    @property
    def index_history(self) -> tuple[IndexRevision, ...]:
        return self._index_history

    def recall(self, *, turn: int) -> None:
        _require_turn(turn, "turn")
        floor = self._last_recalled_turn if self._last_recalled_turn is not None else self._written_turn
        if turn < floor:
            raise EpisodeValidationException("turn must not go back before the last known turn")
        self._recall_count += 1
        self._last_recalled_turn = turn
        self.add_event(
            EpisodeRecalled(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                episode_id=self._episode_id,
                handle=self._handle,
                turn=turn,
                recall_count=self._recall_count,
            )
        )

    def revise_index(self, index: EpisodeIndex, *, turn: int) -> None:
        _require_turn(turn, "turn")
        history = (*self._index_history, IndexRevision(previous=self._index, revised_turn=turn))
        _require_history(index, history, self._written_turn)
        previous = self._index
        self._index = index
        self._index_history = history
        self.add_event(
            EpisodeIndexRevised(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                episode_id=self._episode_id,
                handle=self._handle,
                previous=previous,
                index=index,
                turn=turn,
            )
        )

    def follows(self, earlier: Episode) -> bool:
        """``earlier`` から呼び出しと目次の直しだけで行き着ける版か。"""
        kept = len(earlier.index_history)
        if self.index_history[:kept] != earlier.index_history:
            return False
        if len(self.index_history) == kept:
            index_kept = self.index == earlier.index
        else:
            index_kept = self.index_history[kept].previous == earlier.index
        recall_kept = earlier.last_recalled_turn is None or (
            self.last_recalled_turn is not None and self.last_recalled_turn >= earlier.last_recalled_turn
        )
        return (
            index_kept
            and recall_kept
            and self.being_id == earlier.being_id
            and self.episode_id == earlier.episode_id
            and self.handle == earlier.handle
            and self.environment_name == earlier.environment_name
            and self.written_turn == earlier.written_turn
            and self.body == earlier.body
            and self.recall_count >= earlier.recall_count
        )


class EpisodeRepository(ABC):
    @abstractmethod
    def add(self, episode: Episode) -> None:
        """エピソードが持つ Being の記録に足す。ID か呼び名がその Being の記録と重なれば ``EpisodeConflictException`` を投げる。"""

    @abstractmethod
    def find_by_handle(self, being_id: BeingId, handle: str) -> Episode | None: ...

    @abstractmethod
    def list_by_being(self, being_id: BeingId) -> tuple[Episode, ...]:
        """足した順に返す。"""

    @abstractmethod
    def save(self, episode: Episode) -> None:
        """エピソードが持つ Being の、同じ ID の記録を置き換える。並びの位置は変えない。

        記録に無ければ ``EpisodeNotFoundException``、記録からの後の版でなければ
        (``Episode.follows``) ``EpisodeConflictException`` を投げる。ためたイベントは取り出して配送器に渡す。
        """

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, episodes: Sequence[Episode]) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。

        ``being_id`` は空のときに誰の記録を消すかに要る。別の Being のエピソードが混ざっていれば ``EpisodeConflictException`` を投げる。
        """


__all__ = [
    "BODY_MAX_LENGTH",
    "INDEX_TEXT_MAX_LENGTH",
    "Episode",
    "EpisodeEvent",
    "EpisodeIndex",
    "EpisodeIndexRevised",
    "EpisodeRecalled",
    "EpisodeRepository",
    "EpisodeWrittenEvent",
    "IndexRevision",
]

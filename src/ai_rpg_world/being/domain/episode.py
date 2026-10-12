"""Being が書いた、目次つきのエピソード。"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace

from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

INDEX_TEXT_MAX_LENGTH = 40
BODY_MAX_LENGTH = 400
HANDLE_PREFIX = "ep_"
HANDLE_MIN_ID_LENGTH = 6


def _require_text(value: object, field_name: str, *, max_length: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EpisodeValidationException(f"{field_name} must be non-blank str")
    if max_length is not None and len(value) > max_length:
        raise EpisodeValidationException(
            f"{field_name} must be at most {max_length} characters, got {len(value)}"
        )


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
        raise EpisodeValidationException(
            f"episode_id must be a lowercase hyphenated UUID: {episode_id!r}"
        )
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
class Episode:
    """1 件で集約の根になる。

    持ち主の BeingId は持たない。保存の側が Being ごとに分ける。
    ターンは世界の時刻ではなく Being の記憶のターン数で、環境を跨いでも進み続ける。
    本文は作ったあと変えない。目次を直すと、前の版を ``index_history`` に残す。
    """

    episode_id: str
    handle: str
    environment_name: str
    written_turn: int
    index: EpisodeIndex
    body: str
    recall_count: int = 0
    last_recalled_turn: int | None = None
    index_history: tuple[IndexRevision, ...] = ()

    def __post_init__(self) -> None:
        hex_id = _id_hex(self.episode_id)
        if not isinstance(self.handle, str):
            raise EpisodeValidationException("handle must be str")
        id_part = self.handle.removeprefix(HANDLE_PREFIX)
        if (
            not self.handle.startswith(HANDLE_PREFIX)
            or len(id_part) < HANDLE_MIN_ID_LENGTH
            or not hex_id.startswith(id_part)
        ):
            raise EpisodeValidationException(
                f"handle {self.handle!r} does not come from episode_id {self.episode_id!r}"
            )
        _require_text(self.environment_name, "environment_name")
        _require_turn(self.written_turn, "written_turn")
        if not isinstance(self.index, EpisodeIndex):
            raise EpisodeValidationException("index must be EpisodeIndex")
        _require_text(self.body, "body", max_length=BODY_MAX_LENGTH)
        if (
            not isinstance(self.recall_count, int)
            or isinstance(self.recall_count, bool)
            or self.recall_count < 0
        ):
            raise EpisodeValidationException("recall_count must be int >= 0")
        if self.recall_count == 0:
            if self.last_recalled_turn is not None:
                raise EpisodeValidationException("last_recalled_turn must be None before any recall")
        else:
            if self.last_recalled_turn is None:
                raise EpisodeValidationException("last_recalled_turn is required after a recall")
            _require_turn(self.last_recalled_turn, "last_recalled_turn")
            if self.last_recalled_turn < self.written_turn:
                raise EpisodeValidationException("last_recalled_turn must be >= written_turn")
        if not isinstance(self.index_history, tuple):
            raise EpisodeValidationException("index_history must be tuple")
        floor = self.written_turn
        for revision in self.index_history:
            if not isinstance(revision, IndexRevision):
                raise EpisodeValidationException("index_history must hold IndexRevision")
            if revision.revised_turn < floor:
                raise EpisodeValidationException(
                    "index_history must be ordered by revised_turn from written_turn"
                )
            floor = revision.revised_turn

    @classmethod
    def write(
        cls,
        *,
        episode_id: str,
        environment_name: str,
        written_turn: int,
        index: EpisodeIndex,
        body: str,
        taken_handles: Collection[str] = (),
    ) -> Episode:
        """``taken_handles`` は同じ Being がもう使っている呼び名。"""
        return cls(
            episode_id=episode_id,
            handle=_handle_for(episode_id, taken_handles),
            environment_name=environment_name,
            written_turn=written_turn,
            index=index,
            body=body,
        )

    def recalled_at(self, *, turn: int) -> Episode:
        _require_turn(turn, "turn")
        floor = self.last_recalled_turn if self.last_recalled_turn is not None else self.written_turn
        if turn < floor:
            raise EpisodeValidationException("turn must not go back before the last known turn")
        return replace(self, recall_count=self.recall_count + 1, last_recalled_turn=turn)

    def with_revised_index(self, index: EpisodeIndex, *, turn: int) -> Episode:
        _require_turn(turn, "turn")
        return replace(
            self,
            index=index,
            index_history=(*self.index_history, IndexRevision(previous=self.index, revised_turn=turn)),
        )

    def follows(self, earlier: Episode) -> bool:
        """``earlier`` から呼び出しと目次の直しだけで行き着ける版か。"""
        return (
            self.episode_id == earlier.episode_id
            and self.handle == earlier.handle
            and self.environment_name == earlier.environment_name
            and self.written_turn == earlier.written_turn
            and self.body == earlier.body
            and self.recall_count >= earlier.recall_count
            and self.index_history[: len(earlier.index_history)] == earlier.index_history
        )


class EpisodeRepository(ABC):
    @abstractmethod
    def add(self, being_id: BeingId, episode: Episode) -> None:
        """ID か呼び名がその Being の記録と重なれば ``EpisodeConflictException`` を投げる。"""

    @abstractmethod
    def find_by_handle(self, being_id: BeingId, handle: str) -> Episode | None: ...

    @abstractmethod
    def list_by_being(self, being_id: BeingId) -> tuple[Episode, ...]:
        """足した順に返す。"""

    @abstractmethod
    def save(self, being_id: BeingId, episode: Episode) -> None:
        """同じ ID の記録を置き換える。並びの位置は変えない。

        記録に無ければ ``EpisodeNotFoundException``、記録からの後の版でなければ
        (``Episode.follows``) ``EpisodeConflictException`` を投げる。
        """

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, episodes: Sequence[Episode]) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。"""


__all__ = [
    "BODY_MAX_LENGTH",
    "INDEX_TEXT_MAX_LENGTH",
    "Episode",
    "EpisodeIndex",
    "EpisodeRepository",
    "IndexRevision",
]

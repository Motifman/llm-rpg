"""Being の短期記憶。直近の出来事と、それより前の流れをつなぐいきさつ (#1824)。

出来事は環境との契約の型 (観測と 1 手) で持ち、ゲームの型を持たない。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Final, Protocol, TypeVar

from ai_rpg_world.being.contract import (
    AgentMove,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryUnpairedResultException,
    ShortTermMemoryValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

RECENT_TURNS: Final = 20
FOLD_TURNS: Final = 10
BACKSTORY_GENERATIONS: Final = 3

_T_co = TypeVar("_T_co", covariant=True)


def _require_turn(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShortTermMemoryValidationException(f"{field_name} must be int >= 0 (got {value!r})")
    return value


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ShortTermMemoryValidationException(f"{field_name} must be non-blank str")


def _require_order(value: object) -> None:
    if value is not None and not isinstance(value, OccurrenceOrder):
        raise ShortTermMemoryValidationException("order must be OccurrenceOrder or None")


class ExperienceReader(Protocol[_T_co]):
    """出来事を種類ごとに読む側。文を作る側や保存の側が、出来事の型を見分けずに済む。"""

    def perceived(self, perception: Perception) -> _T_co: ...

    def attempted(self, attempt: Attempt, result: Observation) -> _T_co: ...

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationResult) -> _T_co: ...

    def attempted_without_result(self, attempt: Attempt) -> _T_co: ...

    def lapsed(self, lapse: Lapse) -> _T_co: ...


class Experience(ABC):
    """短期記憶に残る出来事。``turn`` は、その出来事を見る、または起こした 1 手の番号 (design_decisions D1824-5)。"""

    turn: int

    @property
    @abstractmethod
    def order(self) -> OccurrenceOrder | None: ...

    @abstractmethod
    def show_to(self, reader: ExperienceReader[_T_co]) -> _T_co: ...


@dataclass(frozen=True, kw_only=True)
class Perception(Experience):
    """自分の行動の結果以外の経路で届いた観測。"""

    turn: int
    observation: Observation

    def __post_init__(self) -> None:
        _require_turn(self.turn, "turn")
        if not isinstance(self.observation, Observation):
            raise ShortTermMemoryValidationException("observation must be Observation")
        if isinstance(self.observation.route, OwnActionResult):
            raise ShortTermMemoryValidationException("an own action result belongs to an attempt")

    @property
    def order(self) -> OccurrenceOrder | None:
        return self.observation.order

    def show_to(self, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.perceived(self)


@dataclass(frozen=True, kw_only=True)
class MemoryOperationResult:
    """記憶の道具 (メモ、エピソード、状況の評価) の 1 手に、Being の記憶が返した結果。"""

    call_id: str
    body: str
    time: ObservedTime
    order: OccurrenceOrder | None = None

    def __post_init__(self) -> None:
        _require_text(self.call_id, "call_id")
        _require_text(self.body, "body")
        if not isinstance(self.time, ObservedTime):
            raise ShortTermMemoryValidationException("time must be ObservedTime")
        _require_order(self.order)


@dataclass(frozen=True, kw_only=True)
class Attempt(Experience):
    """Being が選んだ 1 手と、その結果。結果が無いのは、結果を待っているか、来ないまま次の 1 手を選んだとき。"""

    turn: int
    move: AgentMove
    result: Observation | MemoryOperationResult | None = None

    def __post_init__(self) -> None:
        _require_turn(self.turn, "turn")
        if not isinstance(self.move, AgentMove):
            raise ShortTermMemoryValidationException("move must be AgentMove")
        if self.result is not None and _call_id_of(self.result) != self.move.call_id:
            raise ShortTermMemoryValidationException(
                f"result {_call_id_of(self.result)!r} does not answer move {self.move.call_id!r}"
            )

    @property
    def order(self) -> OccurrenceOrder | None:
        return None if self.result is None else self.result.order

    def answered_by(self, result: Observation | MemoryOperationResult, *, turn: int) -> Attempt:
        if _call_id_of(result) != self.move.call_id:
            raise ShortTermMemoryUnpairedResultException(
                f"result {_call_id_of(result)!r} does not answer the awaiting move {self.move.call_id!r}"
            )
        return Attempt(turn=turn, move=self.move, result=result)

    def show_to(self, reader: ExperienceReader[_T_co]) -> _T_co:
        if self.result is None:
            return reader.attempted_without_result(self)
        if isinstance(self.result, MemoryOperationResult):
            return reader.attempted_memory_operation(self, self.result)
        return reader.attempted(self, self.result)


def _call_id_of(result: object) -> str:
    if isinstance(result, MemoryOperationResult):
        return result.call_id
    if isinstance(result, Observation) and isinstance(result.route, OwnActionResult):
        return result.route.call_id
    raise ShortTermMemoryValidationException(
        "a result must be an own action result or a memory operation result"
    )


@dataclass(frozen=True, kw_only=True)
class Lapse(Experience):
    """1 手を出せなかったこと (迷った、LLM の呼び出しが失敗した、道具を選ばず文章を返した)。"""

    turn: int
    body: str
    time: ObservedTime
    order: OccurrenceOrder | None = None

    def __post_init__(self) -> None:
        _require_turn(self.turn, "turn")
        _require_text(self.body, "body")
        if not isinstance(self.time, ObservedTime):
            raise ShortTermMemoryValidationException("time must be ObservedTime")
        _require_order(self.order)

    def show_to(self, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.lapsed(self)


@dataclass(frozen=True, kw_only=True)
class Backstory:
    """ここまでのいきさつ。出来事そのものはエピソードが持ち、いきさつはその間の流れと気分を持つ (#1824)。"""

    flow: str
    mood: str
    written_turn: int

    def __post_init__(self) -> None:
        if not isinstance(self.flow, str) or not self.flow.strip():
            raise ShortTermMemoryValidationException("flow must be non-blank str")
        if not isinstance(self.mood, str):
            raise ShortTermMemoryValidationException("mood must be str")
        _require_turn(self.written_turn, "written_turn")


@dataclass(frozen=True, kw_only=True)
class Fold:
    """``fold`` が外した出来事と、そのときのいきさつと、外したあとの短期記憶。"""

    folded: tuple[Experience, ...]
    backstories: tuple[Backstory, ...]
    memory: ShortTermMemory


@dataclass(frozen=True, kw_only=True)
class ShortTermMemory:
    """Being ごとに 1 つ。持ち主の ``BeingId`` は持たず、保存の側が Being ごとに分ける。

    ``recent_from`` は直近の範囲の始まりのターン。``awaiting`` は結果を待っている 1 手。
    """

    experiences: tuple[Experience, ...] = ()
    backstories: tuple[Backstory, ...] = ()
    recent_from: int = 1
    awaiting: Attempt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.experiences, tuple) or not all(
            isinstance(e, Experience) for e in self.experiences
        ):
            raise ShortTermMemoryValidationException("experiences must be a tuple of Experience")
        if not isinstance(self.backstories, tuple) or not all(
            isinstance(b, Backstory) for b in self.backstories
        ):
            raise ShortTermMemoryValidationException("backstories must be a tuple of Backstory")
        if _require_turn(self.recent_from, "recent_from") < 1:
            raise ShortTermMemoryValidationException("recent_from must be >= 1")
        turns = [e.turn for e in self.experiences]
        if turns != sorted(turns):
            raise ShortTermMemoryValidationException("experiences must be in turn order")
        if turns and turns[0] < self.recent_from:
            raise ShortTermMemoryValidationException("experiences must be within the recent range")
        if self.awaiting is not None and (
            not isinstance(self.awaiting, Attempt) or self.awaiting.result is not None
        ):
            raise ShortTermMemoryValidationException("awaiting must be an Attempt without result")
        if self.awaiting is not None and self.awaiting.turn < self.recent_from:
            raise ShortTermMemoryValidationException("awaiting must be within the recent range")
        if len(self.backstories) > BACKSTORY_GENERATIONS:
            raise ShortTermMemoryValidationException(
                f"at most {BACKSTORY_GENERATIONS} backstories, got {len(self.backstories)}"
            )
        written = [b.written_turn for b in self.backstories]
        if written != sorted(written):
            raise ShortTermMemoryValidationException("backstories must be in written order")

    @classmethod
    def empty(cls) -> ShortTermMemory:
        return cls()

    def perceive(self, observation: Observation, *, current_turn: int) -> ShortTermMemory:
        """観測は 1 手を選ぶ前に届き、次の 1 手がそれを見る。"""
        turn = _require_turn(current_turn, "current_turn") + 1
        return self._with(Perception(turn=turn, observation=observation))

    def act(self, move: AgentMove, *, current_turn: int) -> ShortTermMemory:
        """前の 1 手の結果がまだ来ていなければ、前の 1 手を結果の分からない試みとして残す。"""
        memory = self if self.awaiting is None else self._with(self.awaiting)
        attempt = Attempt(turn=_require_turn(current_turn, "current_turn"), move=move)
        return replace(memory, awaiting=attempt)

    def receive_result(
        self, result: Observation | MemoryOperationResult, *, current_turn: int
    ) -> ShortTermMemory:
        if self.awaiting is None:
            raise ShortTermMemoryUnpairedResultException(
                f"no move is awaiting the result {_call_id_of(result)!r}"
            )
        attempt = self.awaiting.answered_by(result, turn=_require_turn(current_turn, "current_turn"))
        return replace(self._with(attempt), awaiting=None)

    def lapse(
        self,
        *,
        body: str,
        time: ObservedTime,
        current_turn: int,
        order: OccurrenceOrder | None = None,
    ) -> ShortTermMemory:
        lapse = Lapse(turn=_require_turn(current_turn, "current_turn"), body=body, time=time, order=order)
        return self._with(lapse)

    def recent(self) -> tuple[Experience, ...]:
        """ターンの順に、同じ環境が続く間は起きた順に並べる。起きた順を持たない出来事は動かさない。"""
        ordered: list[Experience] = []
        run: list[Experience] = []
        for experience in self.experiences:
            if run and not _same_environment(run[-1], experience):
                ordered.extend(_in_occurrence_order(run))
                run = []
            run.append(experience)
        ordered.extend(_in_occurrence_order(run))
        return tuple(ordered)

    def fold(self, *, current_turn: int) -> Fold | None:
        """直近の範囲が ``RECENT_TURNS`` に届いていれば、古い ``FOLD_TURNS`` ターン分を外した値を返す。

        範囲は ``recent_from`` から今のターンまでで、出来事の無いターンも 1 つと数える。
        外すターンに選んだまま結果の来ない 1 手は、結果の分からない試みとして一緒に外す。
        """
        if _require_turn(current_turn, "current_turn") - self.recent_from + 1 < RECENT_TURNS:
            return None
        recent_from = self.recent_from + FOLD_TURNS
        source, awaiting = self, self.awaiting
        if awaiting is not None and awaiting.turn < recent_from:
            source, awaiting = self._with(awaiting), None
        return Fold(
            folded=tuple(e for e in source.experiences if e.turn < recent_from),
            backstories=self.backstories,
            memory=replace(
                source,
                experiences=tuple(e for e in source.experiences if e.turn >= recent_from),
                recent_from=recent_from,
                awaiting=awaiting,
            ),
        )

    def add_backstory(self, backstory: Backstory) -> ShortTermMemory:
        return replace(self, backstories=(*self.backstories, backstory)[-BACKSTORY_GENERATIONS:])

    def _with(self, experience: Experience) -> ShortTermMemory:
        """同じ番号の出来事のあと、次の番号の出来事の前に入れる。"""
        index = sum(1 for e in self.experiences if e.turn <= experience.turn)
        return replace(
            self,
            experiences=(*self.experiences[:index], experience, *self.experiences[index:]),
        )


def _same_environment(left: Experience, right: Experience) -> bool:
    return (
        left.order is not None
        and right.order is not None
        and left.order.environment == right.order.environment
    )


def _in_occurrence_order(run: list[Experience]) -> list[Experience]:
    if len(run) < 2:
        return run
    return sorted(run, key=lambda experience: experience.order)  # type: ignore[arg-type, return-value]


class ShortTermMemoryRepository(ABC):
    @abstractmethod
    def get(self, being_id: BeingId) -> ShortTermMemory:
        """まだ何も覚えていない Being には空の短期記憶を返す。"""

    @abstractmethod
    def save(self, being_id: BeingId, memory: ShortTermMemory) -> None: ...

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, memory: ShortTermMemory) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。"""


__all__ = [
    "BACKSTORY_GENERATIONS",
    "FOLD_TURNS",
    "RECENT_TURNS",
    "Attempt",
    "Backstory",
    "Experience",
    "ExperienceReader",
    "Fold",
    "Lapse",
    "MemoryOperationResult",
    "Perception",
    "ShortTermMemory",
    "ShortTermMemoryRepository",
]

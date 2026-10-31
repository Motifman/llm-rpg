"""Being の短期記憶。直近の出来事と、それより前の流れをつなぐいきさつ (#1824)。

出来事は環境との契約の型 (観測と 1 手) で持ち、ゲームの型を持たない。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Protocol, TypeVar

from ai_rpg_world.being.contract import (
    AgentMove,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryStaleBackstoryException,
    ShortTermMemoryUnpairedResultException,
    ShortTermMemoryValidationException,
)
from ai_rpg_world.eventing import AggregateRoot, DomainEvent

RECENT_TURNS: Final = 20
FOLD_TURNS: Final = 10
BACKSTORY_GENERATIONS: Final = 3
# いきさつを待ち始めてからこのターン数経っても届かなければ、遅れていることを知らせる。
# 上限 (FORCED_FOLD_TURNS) まで待つ間に 1 回知らせられる長さ (design_decisions D1824-11)。
BACKSTORY_OVERDUE_TURNS: Final = 10
# 直近の範囲がここまで伸びたら、いきさつを待たずに古いターンを外す (外す数の 2 回分を待つ)。
FORCED_FOLD_TURNS: Final = RECENT_TURNS + 2 * FOLD_TURNS

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

    def attempted_memory_operation(self, attempt: Attempt, result: MemoryOperationOutcome) -> _T_co: ...

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


class Outcome(ABC):
    """Being が選んだ 1 手の結果。読む側には、結果の種類に合うメソッドで渡す。"""

    @property
    @abstractmethod
    def order(self) -> OccurrenceOrder | None: ...

    @abstractmethod
    def answers(self, call_id: str) -> bool:
        """呼び出しの ID が ``call_id`` の 1 手に答えた結果か。"""

    def fits(self, call_id: str) -> bool:
        """呼び出しの ID が ``call_id`` の 1 手の結果として持てるか。"""
        return self.answers(call_id)

    @abstractmethod
    def show_to(self, attempt: Attempt, reader: ExperienceReader[_T_co]) -> _T_co: ...


@dataclass(frozen=True)
class ObservedOutcome(Outcome):
    """環境 (ゲーム) が返した、自分の行動の結果の観測。"""

    observation: Observation

    def __post_init__(self) -> None:
        if not isinstance(self.observation, Observation) or not isinstance(self.observation.route, OwnActionResult):
            raise ShortTermMemoryValidationException("an observed outcome must be an own action result")

    @property
    def order(self) -> OccurrenceOrder | None:
        return self.observation.order

    def answers(self, call_id: str) -> bool:
        return self.observation.route.call_id == call_id  # type: ignore[union-attr]

    def show_to(self, attempt: Attempt, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.attempted(attempt, self.observation)


@dataclass(frozen=True, kw_only=True)
class MemoryOperationOutcome(Outcome):
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

    def answers(self, call_id: str) -> bool:
        return self.call_id == call_id

    def show_to(self, attempt: Attempt, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.attempted_memory_operation(attempt, self)


@dataclass(frozen=True)
class UnknownOutcome(Outcome):
    """結果が分からない。結果を待っている間と、来ないまま次の 1 手を選んだとき。どの 1 手にも答えていない。"""

    @property
    def order(self) -> OccurrenceOrder | None:
        return None

    def answers(self, call_id: str) -> bool:
        return False

    def fits(self, call_id: str) -> bool:
        return True

    def show_to(self, attempt: Attempt, reader: ExperienceReader[_T_co]) -> _T_co:
        return reader.attempted_without_result(attempt)


@dataclass(frozen=True, kw_only=True)
class Attempt(Experience):
    """Being が選んだ 1 手と、その結果。"""

    turn: int
    move: AgentMove
    result: Outcome = UnknownOutcome()

    def __post_init__(self) -> None:
        _require_turn(self.turn, "turn")
        if not isinstance(self.move, AgentMove):
            raise ShortTermMemoryValidationException("move must be AgentMove")
        if not isinstance(self.result, Outcome):
            raise ShortTermMemoryValidationException("result must be Outcome")
        if not self.result.fits(self.move.call_id):
            raise ShortTermMemoryValidationException(f"{self.result!r} does not answer move {self.move.call_id!r}")

    @property
    def order(self) -> OccurrenceOrder | None:
        return self.result.order

    def is_answered(self) -> bool:
        return self.result.answers(self.move.call_id)

    def answered_by(self, result: Outcome, *, turn: int) -> Attempt:
        if not result.answers(self.move.call_id):
            raise ShortTermMemoryUnpairedResultException(
                f"{result!r} does not answer the awaiting move {self.move.call_id!r}"
            )
        return Attempt(turn=turn, move=self.move, result=result)

    def show_to(self, reader: ExperienceReader[_T_co]) -> _T_co:
        return self.result.show_to(self, reader)


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
    """ここまでのいきさつ。出来事そのものはエピソードが持ち、いきさつはその間の流れと気分を持つ (#1824)。

    ``until_turn`` は、まとめた出来事の範囲の終わりのターン。
    """

    flow: str
    mood: str
    written_turn: int
    until_turn: int

    def __post_init__(self) -> None:
        if not isinstance(self.flow, str) or not self.flow.strip():
            raise ShortTermMemoryValidationException("flow must be non-blank str")
        if not isinstance(self.mood, str):
            raise ShortTermMemoryValidationException("mood must be str")
        _require_turn(self.written_turn, "written_turn")
        _require_turn(self.until_turn, "until_turn")


@dataclass(frozen=True, kw_only=True)
class AwaitedBackstory:
    """届くのを待っている、``until_turn`` までの出来事をまとめたいきさつ。

    ``since_turn`` は今の待ちを始めたターン (範囲が埋まったとき、または遅れを知らせたとき)。
    """

    until_turn: int
    since_turn: int

    def __post_init__(self) -> None:
        _require_turn(self.until_turn, "until_turn")
        _require_turn(self.since_turn, "since_turn")


@dataclass(frozen=True, kw_only=True)
class ShortTermMemoryEvent(DomainEvent):
    """短期記憶の集約がためるイベント。"""

    being_id: BeingId


@dataclass(frozen=True, kw_only=True)
class _RangeToSummarize(ShortTermMemoryEvent):
    """``until_turn`` までの出来事を、いきさつにまとめたい範囲として持つイベントの共通の欄。

    ``experiences`` は ``recent()`` と同じ順。``backstories`` はそのとき持っていたいきさつ。
    """

    turn: int
    until_turn: int
    experiences: tuple[Experience, ...]
    backstories: tuple[Backstory, ...]

    @property
    def latest_backstory(self) -> Backstory | None:
        """新しいいきさつが続きを書く、いま持っているいちばん新しいいきさつ。"""
        return self.backstories[-1] if self.backstories else None


@dataclass(frozen=True, kw_only=True)
class ShortTermMemoryRangeFilledEvent(_RangeToSummarize):
    """直近の範囲が ``RECENT_TURNS`` に届いた。古い ``until_turn`` までの出来事は、いきさつが届くまで外さない。"""


@dataclass(frozen=True, kw_only=True)
class ShortTermMemoryBackstoryOverdueEvent(_RangeToSummarize):
    """待っているいきさつが、待ち始めてから ``BACKSTORY_OVERDUE_TURNS`` 経っても届かない。範囲は変わらない。"""


@dataclass(frozen=True, kw_only=True)
class ShortTermMemoryOldestTurnsDroppedEvent(ShortTermMemoryEvent):
    """直近の範囲が ``FORCED_FOLD_TURNS`` に届いたので、いきさつを待たずに ``until_turn`` までの出来事を外した。``dropped`` は ``recent()`` と同じ順。"""

    turn: int
    until_turn: int
    dropped: tuple[Experience, ...]


@dataclass(frozen=True, kw_only=True)
class ShortTermMemoryBackstoryAddedEvent(ShortTermMemoryEvent):
    """いきさつが入り、まとめた範囲までの出来事を外した。``dropped`` は ``recent()`` と同じ順で、上限で先に外していれば空。

    ``truncated`` は、書いたときに上限を超えて切り詰めた項目と切り詰める前の長さ。いきさつ自体は持たない。
    """

    backstory: Backstory
    dropped: tuple[Experience, ...]
    truncated: Mapping[str, int] = field(default_factory=dict)


class ShortTermMemory(AggregateRoot[ShortTermMemoryEvent]):
    """Being ごとに 1 つある、直近の出来事といきさつを持つ集約 (design_decisions D1824-9)。

    操作は中身を書き換え、値を返さない。決まりに反する操作は例外を投げ、中身もためたイベントも変えない。
    ``recent_from`` は直近の範囲の始まりのターン。``awaiting`` は結果を待っている 1 手。
    ``awaited_backstory`` は、届くのを待っているいきさつ。
    """

    def __init__(
        self,
        being_id: BeingId,
        *,
        experiences: tuple[Experience, ...] = (),
        backstories: tuple[Backstory, ...] = (),
        recent_from: int = 1,
        awaiting: Attempt | None = None,
        awaited_backstory: AwaitedBackstory | None = None,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise ShortTermMemoryValidationException("being_id must be BeingId")
        super().__init__()
        self._being_id = being_id
        self._become(experiences, backstories, recent_from, awaiting, awaited_backstory)

    @classmethod
    def empty(cls, being_id: BeingId) -> ShortTermMemory:
        return cls(being_id)

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def experiences(self) -> tuple[Experience, ...]:
        """覚えた順 (ターンの順) の出来事。プロンプトに出す順は ``recent()``。"""
        return self._experiences

    @property
    def backstories(self) -> tuple[Backstory, ...]:
        return self._backstories

    @property
    def recent_from(self) -> int:
        return self._recent_from

    @property
    def awaiting(self) -> Attempt | None:
        return self._awaiting

    @property
    def awaited_backstory(self) -> AwaitedBackstory | None:
        return self._awaited

    def is_empty(self) -> bool:
        return (
            not self._experiences
            and not self._backstories
            and self._recent_from == 1
            and self._awaiting is None
            and self._awaited is None
        )

    def perceive(self, observation: Observation, *, current_turn: int) -> None:
        """観測は 1 手を選ぶ前に届き、次の 1 手がそれを見る。"""
        turn = _require_turn(current_turn, "current_turn") + 1
        experiences = self._with(Perception(turn=turn, observation=observation))
        self._become(experiences, self._backstories, self._recent_from, self._awaiting, self._awaited)

    def act(self, move: AgentMove, *, current_turn: int) -> None:
        """前の 1 手の結果がまだ来ていなければ、前の 1 手を結果の分からない試みとして残す。"""
        attempt = Attempt(turn=_require_turn(current_turn, "current_turn"), move=move)
        experiences = self._experiences if self._awaiting is None else self._with(self._awaiting)
        self._become(experiences, self._backstories, self._recent_from, attempt, self._awaited)

    def receive_result(self, result: Outcome, *, current_turn: int) -> None:
        if self._awaiting is None:
            raise ShortTermMemoryUnpairedResultException(f"no move is awaiting {result!r}")
        attempt = self._awaiting.answered_by(result, turn=_require_turn(current_turn, "current_turn"))
        self._become(self._with(attempt), self._backstories, self._recent_from, None, self._awaited)

    def lapse(
        self,
        *,
        body: str,
        time: ObservedTime,
        current_turn: int,
        order: OccurrenceOrder | None = None,
    ) -> None:
        lapse = Lapse(turn=_require_turn(current_turn, "current_turn"), body=body, time=time, order=order)
        self._become(self._with(lapse), self._backstories, self._recent_from, self._awaiting, self._awaited)

    def recent(self) -> tuple[Experience, ...]:
        """ターンの順に、同じ環境が続く間は起きた順に並べる。起きた順を持たない出来事は動かさない。"""
        return _in_recent_order(self._experiences)

    def unsummarized(self) -> tuple[Experience, ...]:
        """範囲が埋まったときに、いきさつとエピソードの材料として渡していない出来事。``recent()`` と同じ順。

        いきさつを待っていれば、待っている範囲より後の出来事。結果を待っている 1 手も、結果の分からない試みとして含める。
        """
        experiences = self._experiences if self._awaiting is None else self._with(self._awaiting)
        until_turn = self._awaited.until_turn if self._awaited is not None else self._recent_from - 1
        return _in_recent_order(tuple(e for e in experiences if e.turn > until_turn))

    def end_turn(self, *, turn: int) -> None:
        """ターンの終わりに、直近の範囲の大きさを見る (design_decisions D1824-11、D1824-17)。

        範囲は ``recent_from`` から今のターンまでで、出来事の無いターンも 1 つと数える。

        - ``FORCED_FOLD_TURNS`` に届いたら、いきさつを待たずに古い ``FOLD_TURNS`` ターン分を外し、
          ``ShortTermMemoryOldestTurnsDroppedEvent`` をためる
        - いきさつを待っておらず ``RECENT_TURNS`` に届いたら、古い ``FOLD_TURNS`` ターン分のいきさつを待ち始め、
          ``ShortTermMemoryRangeFilledEvent`` をためる。出来事はまだ外さない
        - 待ち始めてから ``BACKSTORY_OVERDUE_TURNS`` 経っても届かなければ、待ち始めたターンを今のターンに進め、
          ``ShortTermMemoryBackstoryOverdueEvent`` をためる
        """
        size = _require_turn(turn, "turn") - self._recent_from + 1
        if size >= FORCED_FOLD_TURNS:
            until_turn = self._recent_from + FOLD_TURNS - 1
            dropped = self._forget_until(until_turn)
            self._add(ShortTermMemoryOldestTurnsDroppedEvent, turn=turn, until_turn=until_turn, dropped=dropped)
        if self._awaited is None:
            if size >= RECENT_TURNS:
                until_turn = self._recent_from + FOLD_TURNS - 1
                self._await(until_turn, since_turn=turn)
                self._add(
                    ShortTermMemoryRangeFilledEvent, turn=turn, until_turn=until_turn, **self._material(until_turn)
                )
            return
        if turn - self._awaited.since_turn >= BACKSTORY_OVERDUE_TURNS:
            until_turn = self._awaited.until_turn
            self._await(until_turn, since_turn=turn)
            self._add(
                ShortTermMemoryBackstoryOverdueEvent, turn=turn, until_turn=until_turn, **self._material(until_turn)
            )

    def add_backstory(self, backstory: Backstory, *, truncated: Mapping[str, int] | None = None) -> None:
        """届いたいきさつを入れ、まとめた範囲までの出来事を外す。同じか前の範囲までのいきさつは例外で断る。

        ``truncated`` (書いたときに切り詰めた項目と元の長さ) は、いきさつが入ったイベントにだけ載せる。
        """
        if not isinstance(backstory, Backstory):
            raise ShortTermMemoryValidationException("backstory must be Backstory")
        latest = self._backstories[-1].until_turn if self._backstories else None
        if latest is not None and backstory.until_turn <= latest:
            raise ShortTermMemoryStaleBackstoryException(
                f"backstory until turn {backstory.until_turn} is not later than the latest one until turn {latest}"
            )
        backstories = (*self._backstories, backstory)[-BACKSTORY_GENERATIONS:]
        awaited = self._awaited
        if awaited is not None and backstory.until_turn >= awaited.until_turn:
            awaited = None
        dropped = _in_recent_order(self._up_to(backstory.until_turn))
        experiences, recent_from, awaiting = self._after_forgetting(backstory.until_turn)
        self._become(experiences, backstories, recent_from, awaiting, awaited)
        self._add(
            ShortTermMemoryBackstoryAddedEvent, backstory=backstory, dropped=dropped, truncated=dict(truncated or {})
        )

    def _await(self, until_turn: int, *, since_turn: int) -> None:
        awaited = AwaitedBackstory(until_turn=until_turn, since_turn=since_turn)
        self._become(self._experiences, self._backstories, self._recent_from, self._awaiting, awaited)

    def _material(self, until_turn: int) -> dict[str, Any]:
        """いきさつとエピソードの材料。外す範囲の出来事と、今のいきさつ。"""
        return {"experiences": _in_recent_order(self._up_to(until_turn)), "backstories": self._backstories}

    def _up_to(self, until_turn: int) -> tuple[Experience, ...]:
        """``until_turn`` までの出来事。そのターンまでに選んだまま結果の来ない 1 手も含む。"""
        awaiting = self._awaiting
        experiences = self._experiences if awaiting is None or awaiting.turn > until_turn else self._with(awaiting)
        return tuple(e for e in experiences if e.turn <= until_turn)

    def _forget_until(self, until_turn: int) -> tuple[Experience, ...]:
        """``until_turn`` までの出来事を外す。その範囲までのいきさつを待っていたなら、範囲がもう無いので待つのをやめる。"""
        dropped = _in_recent_order(self._up_to(until_turn))
        experiences, recent_from, awaiting = self._after_forgetting(until_turn)
        awaited = self._awaited
        if awaited is not None and awaited.until_turn <= until_turn:
            awaited = None
        self._become(experiences, self._backstories, recent_from, awaiting, awaited)
        return dropped

    def _after_forgetting(self, until_turn: int) -> tuple[tuple[Experience, ...], int, Attempt | None]:
        """``until_turn`` までを外したあとの出来事、範囲の始まり、待っている 1 手。外すターンに選んだまま結果の来ない 1 手も外す。"""
        recent_from = max(self._recent_from, until_turn + 1)
        experiences, awaiting = self._experiences, self._awaiting
        if awaiting is not None and awaiting.turn < recent_from:
            experiences, awaiting = self._with(awaiting), None
        return tuple(e for e in experiences if e.turn >= recent_from), recent_from, awaiting

    def _add(self, event_type: type[ShortTermMemoryEvent], **fields: Any) -> None:
        self.add_event(
            event_type(
                event_id=uuid.uuid4().int,
                occurred_at=datetime.now(timezone.utc),
                being_id=self._being_id,
                **fields,
            )
        )

    def _with(self, experience: Experience) -> tuple[Experience, ...]:
        """同じ番号の出来事のあと、次の番号の出来事の前に入れる。"""
        index = sum(1 for e in self._experiences if e.turn <= experience.turn)
        return (*self._experiences[:index], experience, *self._experiences[index:])

    def _become(
        self,
        experiences: tuple[Experience, ...],
        backstories: tuple[Backstory, ...],
        recent_from: int,
        awaiting: Attempt | None,
        awaited: AwaitedBackstory | None,
    ) -> None:
        """決まりを確かめてから書き換える。決まりに反すれば何も変えずに例外を投げる。"""
        if not isinstance(experiences, tuple) or not all(isinstance(e, Experience) for e in experiences):
            raise ShortTermMemoryValidationException("experiences must be a tuple of Experience")
        if not isinstance(backstories, tuple) or not all(isinstance(b, Backstory) for b in backstories):
            raise ShortTermMemoryValidationException("backstories must be a tuple of Backstory")
        if _require_turn(recent_from, "recent_from") < 1:
            raise ShortTermMemoryValidationException("recent_from must be >= 1")
        turns = [e.turn for e in experiences]
        if turns != sorted(turns):
            raise ShortTermMemoryValidationException("experiences must be in turn order")
        if turns and turns[0] < recent_from:
            raise ShortTermMemoryValidationException("experiences must be within the recent range")
        if awaiting is not None and (not isinstance(awaiting, Attempt) or awaiting.is_answered()):
            raise ShortTermMemoryValidationException("awaiting must be an Attempt without result")
        if awaiting is not None and awaiting.turn < recent_from:
            raise ShortTermMemoryValidationException("awaiting must be within the recent range")
        if len(backstories) > BACKSTORY_GENERATIONS:
            raise ShortTermMemoryValidationException(
                f"at most {BACKSTORY_GENERATIONS} backstories, got {len(backstories)}"
            )
        until = [b.until_turn for b in backstories]
        if until != sorted(set(until)):
            raise ShortTermMemoryValidationException("backstories must cover later turns in order")
        if awaited is not None and (not isinstance(awaited, AwaitedBackstory) or awaited.until_turn < recent_from):
            raise ShortTermMemoryValidationException("the awaited backstory must cover turns within the recent range")
        self._experiences = experiences
        self._backstories = backstories
        self._recent_from = recent_from
        self._awaiting = awaiting
        self._awaited = awaited


def _in_recent_order(experiences: tuple[Experience, ...]) -> tuple[Experience, ...]:
    ordered: list[Experience] = []
    run: list[Experience] = []
    for experience in experiences:
        if run and not _same_environment(run[-1], experience):
            ordered.extend(_in_occurrence_order(run))
            run = []
        run.append(experience)
    ordered.extend(_in_occurrence_order(run))
    return tuple(ordered)


def _same_environment(left: Experience, right: Experience) -> bool:
    return left.order is not None and right.order is not None and left.order.environment == right.order.environment


def _in_occurrence_order(run: list[Experience]) -> list[Experience]:
    if len(run) < 2:
        return run
    return sorted(run, key=lambda experience: experience.order)  # type: ignore[arg-type, return-value]


class ShortTermMemoryRepository(ABC):
    @abstractmethod
    def get(self, being_id: BeingId) -> ShortTermMemory:
        """まだ何も覚えていない Being には空の短期記憶を返す。返した集約を書き換えても、``save`` するまで保存先は変わらない。"""

    @abstractmethod
    def save(self, memory: ShortTermMemory) -> None:
        """保存したあとで渡した集約を書き換えても、保存先は変わらない。ためたイベントは取り出して配送器に渡す。"""

    @abstractmethod
    def replace_all_by_being(self, memory: ShortTermMemory) -> None:
        """記憶の持ち越しから戻すときに使う。空ならその Being の記録を消す。"""


__all__ = [
    "BACKSTORY_GENERATIONS",
    "BACKSTORY_OVERDUE_TURNS",
    "FOLD_TURNS",
    "FORCED_FOLD_TURNS",
    "RECENT_TURNS",
    "Attempt",
    "AwaitedBackstory",
    "Backstory",
    "Experience",
    "ExperienceReader",
    "Lapse",
    "MemoryOperationOutcome",
    "ObservedOutcome",
    "Outcome",
    "Perception",
    "ShortTermMemory",
    "ShortTermMemoryBackstoryAddedEvent",
    "ShortTermMemoryBackstoryOverdueEvent",
    "ShortTermMemoryEvent",
    "ShortTermMemoryOldestTurnsDroppedEvent",
    "ShortTermMemoryRangeFilledEvent",
    "ShortTermMemoryRepository",
    "UnknownOutcome",
]

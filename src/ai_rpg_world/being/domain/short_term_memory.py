"""Being の短期記憶。直近の出来事と、それより前の流れをつなぐいきさつ。

出来事は環境との契約の型 (観測と 1 手) で持ち、ゲームの型を持たない。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai_rpg_world.being.contract import AgentMove, Observation, OwnActionResult, Route
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

BACKSTORY_GENERATIONS = 3


def _require_turn(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ShortTermMemoryValidationException(f"{field_name} must be int >= 0 (got {value!r})")
    return value


def turn_for_event(route: Route, *, current_turn: int) -> int:
    """出来事に付ける手番の番号 (design_decisions D1824-5)。

    観測は 1 手を受け取る前に届き、次の 1 手がそれを見る。自分の行動の結果は、
    時計がその 1 手の番号まで進んだあとに届く。
    """
    _require_turn(current_turn, "current_turn")
    if isinstance(route, OwnActionResult):
        if current_turn == 0:
            raise ShortTermMemoryValidationException("an own action result needs a move before it")
        return current_turn
    return current_turn + 1


@dataclass(frozen=True, kw_only=True)
class RememberedEvent:
    """``move`` は、自分の行動の結果を生んだ 1 手。それ以外の経路では持たない。"""

    turn: int
    observation: Observation
    move: AgentMove | None = None

    def __post_init__(self) -> None:
        _require_turn(self.turn, "turn")
        if not isinstance(self.observation, Observation):
            raise ShortTermMemoryValidationException("observation must be Observation")
        route = self.observation.route
        if not isinstance(route, OwnActionResult):
            if self.move is not None:
                raise ShortTermMemoryValidationException("only an own action result carries a move")
            return
        if not isinstance(self.move, AgentMove):
            raise ShortTermMemoryValidationException("an own action result needs the move that caused it")
        if self.move.call_id != route.call_id:
            raise ShortTermMemoryValidationException(
                f"move {self.move.call_id!r} does not match result {route.call_id!r}"
            )


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


@dataclass(frozen=True)
class ShortTermMemory:
    """Being ごとに 1 つ。持ち主の ``BeingId`` は持たず、保存の側が Being ごとに分ける。"""

    events: tuple[RememberedEvent, ...] = ()
    backstories: tuple[Backstory, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple) or not all(
            isinstance(e, RememberedEvent) for e in self.events
        ):
            raise ShortTermMemoryValidationException("events must be a tuple of RememberedEvent")
        if not isinstance(self.backstories, tuple) or not all(
            isinstance(b, Backstory) for b in self.backstories
        ):
            raise ShortTermMemoryValidationException("backstories must be a tuple of Backstory")
        turns = [e.turn for e in self.events]
        if turns != sorted(turns):
            raise ShortTermMemoryValidationException("events must be in turn order")
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

    def remember(self, event: RememberedEvent) -> ShortTermMemory:
        return ShortTermMemory(events=(*self.events, event), backstories=self.backstories)

    def add_backstory(self, backstory: Backstory) -> ShortTermMemory:
        kept = (*self.backstories, backstory)[-BACKSTORY_GENERATIONS:]
        return ShortTermMemory(events=self.events, backstories=kept)


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
    "Backstory",
    "RememberedEvent",
    "ShortTermMemory",
    "ShortTermMemoryRepository",
    "turn_for_event",
]

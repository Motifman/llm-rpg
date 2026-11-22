from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol, Union, final

from ai_rpg_world.game_world.application.accept_world_time_passage import (
    AcceptWorldTimePassage,
    AcceptWorldTimePassageCommand,
)
from ai_rpg_world.game_world.application.check_readiness_to_act import (
    CheckReadinessToAct,
    CheckReadinessToActCommand,
)
from ai_rpg_world.game_world.application.world_has_ended import WorldHasEnded, WorldHasEndedCommand
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.cast import CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import TurnOutcome, TurnRoundsRepository


@final
@dataclass(frozen=True)
class FinishedTurn:
    person: PersonId
    outcome: TurnOutcome


class TurnTakers(Protocol):
    def take_turns(self, people: Sequence[PersonId]) -> Iterator[FinishedTurn]: ...


@final
@dataclass(frozen=True)
class WorldEnded:
    pass


@final
@dataclass(frozen=True)
class RoundLimitReached:
    pass


PlayStopped = Union[WorldEnded, RoundLimitReached]


@final
@dataclass(frozen=True)
class PlayRoundsCommand:
    world: WorldId


@final
class PlayRounds:
    def __init__(
        self,
        *,
        casts: CastRepository,
        turn_rounds: TurnRoundsRepository,
        turn_takers: TurnTakers,
        check_readiness: CheckReadinessToAct,
        world_has_ended: WorldHasEnded,
        accept_time_passage: AcceptWorldTimePassage,
    ) -> None:
        self._casts = casts
        self._turn_rounds = turn_rounds
        self._turn_takers = turn_takers
        self._check_readiness = check_readiness
        self._world_has_ended = world_has_ended
        self._accept_time_passage = accept_time_passage

    def __call__(self, command: PlayRoundsCommand) -> PlayStopped:
        people = self._casts.get(command.world).people()
        while True:
            if self._world_has_ended(WorldHasEndedCommand()):
                return WorldEnded()
            if self._turn_rounds.get(command.world).has_reached_round_limit():
                return RoundLimitReached()
            stopped = self._play_one_round(command.world, people)
            if stopped is not None:
                return stopped

    def _play_one_round(self, world: WorldId, people: tuple[PersonId, ...]) -> PlayStopped | None:
        rounds = self._turn_rounds.get(world)
        rounds.open_round(self._check_readiness(CheckReadinessToActCommand(people)))
        self._turn_rounds.save(rounds)
        for finished in self._turn_takers.take_turns(rounds.due_turns()):
            # ターンの最中に届いた呼びかけを保存で消さないよう、取り出した写しを持ち続けない
            rounds = self._turn_rounds.get(world)
            rounds.finish_turn(finished.person, finished.outcome)
            self._turn_rounds.save(rounds)
            if self._world_has_ended(WorldHasEndedCommand()):
                return WorldEnded()
        rounds = self._turn_rounds.get(world)
        rounds.close_round()
        self._turn_rounds.save(rounds)
        # 断られるのは世界が終わっていたときだけなので、返事ではなく次の巡りの前の問いで止める
        self._accept_time_passage(AcceptWorldTimePassageCommand())
        return None

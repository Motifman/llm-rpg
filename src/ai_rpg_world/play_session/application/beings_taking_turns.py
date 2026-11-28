from __future__ import annotations

from collections.abc import Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import final

from ai_rpg_world.being.application.choose_action import (
    ActionChosen,
    ActionNotChosen,
    ActionPrompt,
    ActionThought,
    ChooseAction,
    ChooseActionCommand,
    TurnSpentRecalling,
    TurnSpentRevisingIndex,
)
from ai_rpg_world.being.application.end_being_turn import EndBeingTurn, EndBeingTurnCommand
from ai_rpg_world.being.application.receive_action_result import ReceiveActionResult, ReceiveActionResultCommand
from ai_rpg_world.being.contract import OfferedBeingTools
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.working_memory import Closing
from ai_rpg_world.game_world.application.describe_action_result import (
    DescribeActionResult,
    DescribeActionResultCommand,
)
from ai_rpg_world.game_world.application.describe_scene import DescribeScene, DescribeSceneCommand
from ai_rpg_world.game_world.application.mark_body_as_shown import MarkBodyAsShown, MarkBodyAsShownCommand
from ai_rpg_world.game_world.application.offer_action_choices import OfferActionChoices, OfferActionChoicesCommand
from ai_rpg_world.game_world.application.take_chosen_action import TakeChosenAction, TakeChosenActionCommand
from ai_rpg_world.game_world.application.tell_current_time import TellCurrentTime, TellCurrentTimeCommand
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.application.play_rounds import DiscardedChoice, FinishedTurn, TurnsInProgress
from ai_rpg_world.play_session.domain.cast import CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import Acted, ChoiceFailed, TurnOutcome, TurnRoundsRepository, Waited

ChoiceOutcome = ActionChosen | TurnSpentRecalling | TurnSpentRevisingIndex | ActionNotChosen


@final
class BeingTurnSteps:
    def __init__(
        self,
        *,
        world: WorldId,
        casts: CastRepository,
        being_tools: OfferedBeingTools,
        closing: Closing,
        describe_scene: DescribeScene,
        mark_body_as_shown: MarkBodyAsShown,
        offer_choices: OfferActionChoices,
        tell_time: TellCurrentTime,
        choose_action: ChooseAction,
        take_chosen_action: TakeChosenAction,
        describe_result: DescribeActionResult,
        receive_result: ReceiveActionResult,
        end_being_turn: EndBeingTurn,
    ) -> None:
        self.world = world
        self._casts = casts
        self._being_tools = being_tools
        self._closing = closing
        self._describe_scene = describe_scene
        self._mark_body_as_shown = mark_body_as_shown
        self._offer_choices = offer_choices
        self._tell_time = tell_time
        self.choose_action = choose_action
        self._take_chosen_action = take_chosen_action
        self._describe_result = describe_result
        self._receive_result = receive_result
        self._end_being_turn = end_being_turn

    def being_of(self, person: PersonId) -> BeingId:
        return self._casts.get(self.world).being_of(person)

    def command_for(self, person: PersonId) -> ChooseActionCommand:
        cast = self._casts.get(self.world)
        command = ChooseActionCommand(
            being_id=cast.being_of(person),
            orientation=cast.orientation_of(person),
            being_tools=self._being_tools,
            imposed_goal=cast.entry_of(person).imposed_goal,
            scene=self._describe_scene(DescribeSceneCommand(person)),
            closing=self._closing,
            choices=self._offer_choices(OfferActionChoicesCommand(person)),
            now=self._tell_time(TellCurrentTimeCommand()),
        )
        # 「前回」は、この人に最後に渡した場面の値にする。LLM の呼び出しが落ちても場面は渡したので、選ぶ前に覚える
        self._mark_body_as_shown(MarkBodyAsShownCommand(person))
        return command

    def carry_out(self, person: PersonId, chosen: ChoiceOutcome) -> TurnOutcome:
        # LLM は答えたが世界に渡す行動が無いとき (ツールを呼ばない、無いツール、思い出すだけ、目次を直すだけ) は、呼び出しの失敗ではないので
        # 失敗の続きを切り、ターンを使ったものとして次の巡りでまた頼む
        if not isinstance(chosen, ActionChosen):
            return Acted()
        reply = self._take_chosen_action(TakeChosenActionCommand(person, chosen.move))
        result = self._describe_result(DescribeActionResultCommand(reply=reply, call_id=chosen.move.call_id))
        self._receive_result.execute(ReceiveActionResultCommand(being_id=self.being_of(person), result=result))
        return Waited() if reply.was_waiting() else Acted()

    def end_turn(self, person: PersonId) -> None:
        self._end_being_turn.execute(EndBeingTurnCommand(self.being_of(person)))


def _failed(error: Exception) -> ChoiceFailed:
    return ChoiceFailed(f"{type(error).__name__}: {error}")


@final
class BeingsTakingTurnsOneByOne:
    def __init__(self, steps: BeingTurnSteps) -> None:
        self._steps = steps

    def take_turns(self, people: Sequence[PersonId]) -> TurnsInProgress:
        return _TurnsOneByOne(self._steps, people)


@final
class _TurnsOneByOne:
    def __init__(self, steps: BeingTurnSteps, people: Sequence[PersonId]) -> None:
        self._steps = steps
        self._people = tuple(people)

    def __iter__(self) -> Iterator[FinishedTurn]:
        for person in self._people:
            outcome = self._take_turn(person)
            self._steps.end_turn(person)
            yield FinishedTurn(person, outcome)

    def let_go(self) -> tuple[DiscardedChoice, ...]:
        return ()

    def _take_turn(self, person: PersonId) -> TurnOutcome:
        command = self._steps.command_for(person)
        try:
            chosen = self._steps.choose_action.execute(command)
        # LLM の呼び出しの失敗は provider ごとに型が違うので、型で絞らずに ChooseAction ごと囲み、呼び出しが落ちたターンとして数える
        except Exception as error:
            return _failed(error)
        return self._steps.carry_out(person, chosen)


@final
class BeingsTakingTurnsAtOnce:
    def __init__(self, steps: BeingTurnSteps, turn_rounds: TurnRoundsRepository) -> None:
        self._steps = steps
        self._turn_rounds = turn_rounds

    def take_turns(self, people: Sequence[PersonId]) -> TurnsInProgress:
        return _TurnsAtOnce(self._steps, self._turn_rounds, people)


@final
class _TurnsAtOnce:
    """考える段だけを worker で並べ、記憶と世界に触る段は呼んだスレッドで、返事が返った順に進める。"""

    def __init__(self, steps: BeingTurnSteps, turn_rounds: TurnRoundsRepository, people: Sequence[PersonId]) -> None:
        self._steps = steps
        self._turn_rounds = turn_rounds
        self._people = tuple(people)
        self._executor: ThreadPoolExecutor | None = None
        self._thinking: dict[Future[ActionThought], PersonId] = {}
        self._let_go = False

    def __iter__(self) -> Iterator[FinishedTurn]:
        # 全員が巡りの頭の同じ世界を見て選ぶよう、誰かの行為を確定させる前に全員の場面を組む
        prompts: list[tuple[PersonId, ActionPrompt]] = []
        failed_to_prompt: list[tuple[PersonId, ChoiceFailed]] = []
        for person in self._people:
            command = self._steps.command_for(person)
            try:
                prompts.append((person, self._steps.choose_action.prompt(command)))
            except Exception as error:
                failed_to_prompt.append((person, _failed(error)))
        for person, failure in failed_to_prompt:
            yield self._finished(person, failure)
        if not prompts:
            return
        rounds = self._turn_rounds.get(self._steps.world)
        rounds.begin_choosing(tuple(person for person, _ in prompts))
        self._turn_rounds.save(rounds)
        self._executor = ThreadPoolExecutor(max_workers=len(prompts), thread_name_prefix="being_thinking")
        self._thinking = {self._executor.submit(self._steps.choose_action.think, prompt): p for p, prompt in prompts}
        try:
            for future in as_completed(tuple(self._thinking)):
                person = self._thinking.pop(future)
                rounds = self._turn_rounds.get(self._steps.world)
                rounds.finish_choosing(person)
                self._turn_rounds.save(rounds)
                yield self._finished(person, self._settled(person, future))
        finally:
            self._executor.shutdown(wait=False)

    def let_go(self) -> tuple[DiscardedChoice, ...]:
        if self._let_go:
            return ()
        self._let_go = True
        for future in self._thinking:
            future.cancel()
        discarded = tuple(_discarded(person, future) for future, person in self._thinking.items())
        self._thinking = {}
        if self._executor is not None:
            self._executor.shutdown(wait=True)
        return discarded

    def _settled(self, person: PersonId, future: Future[ActionThought]) -> TurnOutcome:
        try:
            chosen = self._steps.choose_action.settle(future.result())
        except Exception as error:
            return _failed(error)
        return self._steps.carry_out(person, chosen)

    def _finished(self, person: PersonId, outcome: TurnOutcome) -> FinishedTurn:
        self._steps.end_turn(person)
        return FinishedTurn(person, outcome)


def _discarded(person: PersonId, future: Future[ActionThought]) -> DiscardedChoice:
    if future.cancelled():
        return DiscardedChoice(person=person, exchange=None, failure=None)
    # 走っている呼び出しは止められないので、返るまで待つ。待たないと、遊びを終えたあとに返事が届く
    error = future.exception()
    if error is not None:
        return DiscardedChoice(person=person, exchange=None, failure=f"{type(error).__name__}: {error}")
    return DiscardedChoice(person=person, exchange=future.result().exchange, failure=None)

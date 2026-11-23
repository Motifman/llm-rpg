from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import final

from ai_rpg_world.being.application.choose_action import ActionChosen, ChooseAction, ChooseActionCommand
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
from ai_rpg_world.play_session.application.play_rounds import FinishedTurn, TurnTakers
from ai_rpg_world.play_session.domain.cast import CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import Acted, ChoiceFailed, TurnOutcome, Waited


@final
class BeingsTakingTurnsOneByOne(TurnTakers):
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
        self._world = world
        self._casts = casts
        self._being_tools = being_tools
        self._closing = closing
        self._describe_scene = describe_scene
        self._mark_body_as_shown = mark_body_as_shown
        self._offer_choices = offer_choices
        self._tell_time = tell_time
        self._choose_action = choose_action
        self._take_chosen_action = take_chosen_action
        self._describe_result = describe_result
        self._receive_result = receive_result
        self._end_being_turn = end_being_turn

    def take_turns(self, people: Sequence[PersonId]) -> Iterator[FinishedTurn]:
        for person in people:
            being_id = self._casts.get(self._world).being_of(person)
            outcome = self._take_turn(person, being_id)
            self._end_being_turn.execute(EndBeingTurnCommand(being_id))
            yield FinishedTurn(person, outcome)

    def _take_turn(self, person: PersonId, being_id: BeingId) -> TurnOutcome:
        cast = self._casts.get(self._world)
        command = ChooseActionCommand(
            being_id=being_id,
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
        try:
            chosen = self._choose_action.execute(command)
        # LLM の呼び出しの失敗は provider ごとに型が違うので、型で絞らずに ChooseAction ごと囲み、呼び出しが落ちたターンとして数える
        except Exception as error:
            return ChoiceFailed(f"{type(error).__name__}: {error}")
        # LLM は答えたが世界に渡す行動が無いとき (ツールを呼ばない、無いツール、思い出すだけ) は、呼び出しの失敗ではないので
        # 失敗の続きを切り、ターンを使ったものとして次の巡りでまた頼む
        if not isinstance(chosen, ActionChosen):
            return Acted()
        reply = self._take_chosen_action(TakeChosenActionCommand(person, chosen.move))
        result = self._describe_result(DescribeActionResultCommand(reply=reply, call_id=chosen.move.call_id))
        self._receive_result.execute(ReceiveActionResultCommand(being_id=being_id, result=result))
        return Waited() if reply.was_waiting() else Acted()

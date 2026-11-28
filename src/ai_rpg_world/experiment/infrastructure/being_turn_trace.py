from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any, final
from uuid import uuid4

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
)
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
from ai_rpg_world.being.application.receive_action_result import ReceiveActionResult, ReceiveActionResultCommand
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.experiment.infrastructure.game_world_trace import GameWorldTrace, GameWorldTraceKind
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.application.beings_taking_turns import ChoiceOutcome


def prompt_sha256(prompt: ActionPrompt) -> str:
    text = json.dumps({"messages": prompt.messages, "tools": prompt.definitions}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@final
class TracedChooseAction:
    """LLM とのやりとりはドメインの事実ではなくイベントにならないので、ここで受け取って書く (D2233)。"""

    def __init__(
        self,
        inner: ChooseAction,
        *,
        trace: Callable[[], GameWorldTrace],
        person_of: Callable[[BeingId], PersonId],
        prompts: Callable[[], PromptDatasetCaptureSink | None],
        run_id: Callable[[], str],
        player_number_of: Callable[[PersonId], int],
    ) -> None:
        self._inner = inner
        self._trace = trace
        self._person_of = person_of
        self._prompts = prompts
        self._run_id = run_id
        self._player_number_of = player_number_of
        self._lock = threading.Lock()
        self._thinking_ms: dict[int, int] = {}
        self._turns: dict[PersonId, int] = {}

    def execute(self, command: ChooseActionCommand) -> ChoiceOutcome:
        return self.settle(self.think(self.prompt(command)))

    def prompt(self, command: ChooseActionCommand) -> ActionPrompt:
        return self._inner.prompt(command)

    def think(self, prompt: ActionPrompt) -> ActionThought:
        started = time.monotonic()
        thought = self._inner.think(prompt)
        with self._lock:
            self._thinking_ms[id(thought)] = int((time.monotonic() - started) * 1000)
        return thought

    def settle(self, thought: ActionThought) -> ChoiceOutcome:
        try:
            outcome = self._inner.settle(thought)
        finally:
            with self._lock:
                thinking_ms = self._thinking_ms.pop(id(thought), None)
        # 選んだ行動はもう記憶に書いてある。記録を組む途中で落ちても、選べなかったターンにしない
        trace = self._trace()
        trace.guarded(lambda: self._record(trace, thought, outcome, thinking_ms))
        return outcome

    def _record(
        self, trace: GameWorldTrace, thought: ActionThought, outcome: ChoiceOutcome, thinking_ms: int | None
    ) -> None:
        command = thought.prompt.command
        person = self._person_of(command.being_id)
        llm_call_id = f"llm_{uuid4().hex}"
        sha = prompt_sha256(thought.prompt)
        replies = [
            {
                "tool": None if reply.tool_call is None else reply.tool_call.tool_name,
                "arguments": None if reply.tool_call is None else dict(reply.tool_call.arguments),
                "cut_off_while_reasoning": reply.cut_off_while_reasoning,
            }
            for reply in thought.exchange.replies
        ]
        candidate_table = thought.prompt.tools.candidate_table()
        tick = trace.now()
        with self._lock:
            self._turns[person] = turn = self._turns.get(person, 0) + 1
        trace.record_being_turn(
            GameWorldTraceKind.CHOICE,
            person,
            llm_call_id=llm_call_id,
            prompt_sha256=sha,
            prompt_chars=sum(len(m["content"]) for m in thought.prompt.messages),
            thinking_ms=thinking_ms,
            scene=trace.jsonable(command.scene),
            choices=[choice.name for choice in command.choices.choices],
            candidate_table=None if candidate_table is None else candidate_table.text,
            replies=replies,
            **_outcome(outcome, trace.jsonable),
        )
        prompts = self._prompts()
        if prompts is not None:
            prompts.record_call(
                context=PromptDatasetCallContext(
                    llm_call_id=llm_call_id,
                    run_id=self._run_id(),
                    world_id=None,
                    being_id=command.being_id.value,
                    player_id=self._player_number_of(person),
                    persona_id=command.being_id.value,
                    character_name=trace.name_of(person),
                    turn_index=turn,
                    world_tick=tick,
                    provenance={"world": "game_world", "person_id": person.value, "prompt_sha256": sha},
                ),
                request_kwargs={
                    "model": None,
                    "messages": list(thought.prompt.messages),
                    "tools": list(thought.prompt.definitions),
                },
                output={"replies": replies, **_outcome(outcome, trace.jsonable)},
            )


@final
class TracedReceiveActionResult:
    """世界に断られた行為は巻き戻されて出来事が残らず、Being も結果を受けたイベントを出さないので、ここで書く (D2233)。"""

    def __init__(
        self,
        inner: ReceiveActionResult,
        *,
        trace: Callable[[], GameWorldTrace],
        person_of: Callable[[BeingId], PersonId],
    ) -> None:
        self._inner = inner
        self._trace = trace
        self._person_of = person_of

    def execute(self, command: ReceiveActionResultCommand) -> None:
        self._inner.execute(command)
        trace = self._trace()
        # 結果はもう記憶に入り、行為も世界で確定している。記録が落ちても、遊びは変えない
        trace.guarded(
            lambda: trace.record_being_turn(
                GameWorldTraceKind.ACTION_RESULT,
                self._person_of(command.being_id),
                route=trace.jsonable(command.result.route),
                body=trace.jsonable(command.result.body),
            )
        )


def _outcome(outcome: ChoiceOutcome, jsonable: Callable[[object], Any]) -> dict[str, Any]:
    match outcome:
        case ActionChosen():
            return {
                "outcome": "action_chosen",
                "move": {"tool": outcome.move.tool_name, "arguments": dict(outcome.move.arguments)},
                "name_rechoices": len(outcome.name_rechoices),
            }
        case TurnSpentRecalling():
            return {
                "outcome": "recalling",
                "move": {"tool": outcome.move.tool_name, "arguments": dict(outcome.move.arguments)},
            }
        case TurnSpentRevisingIndex():
            return {
                "outcome": "revising_index",
                "move": {"tool": outcome.move.tool_name, "arguments": dict(outcome.move.arguments)},
                "revision": jsonable(outcome.revision),
            }
        case ActionNotChosen():
            return {"outcome": "not_chosen", "requested_tool": outcome.requested_tool, "suggestion": outcome.suggestion}

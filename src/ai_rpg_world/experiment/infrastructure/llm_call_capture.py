from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, final
from uuid import uuid4

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCallContext,
    PromptDatasetCaptureSink,
)
from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ActionPrompt,
    ActionThought,
    ChooseAction,
    ChooseActionCommand,
)
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter, WrittenBackstory
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode_writer import EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience
from ai_rpg_world.being.infrastructure.llm_episode_writer import EpisodeWritingCompletion
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
from ai_rpg_world.play_session.application.beings_taking_turns import ChoiceOutcome

_logger = logging.getLogger(__name__)

CHOOSING_ACTION = "choose_action"
WRITING_EPISODES = "episode_writing"
WRITING_BACKSTORY = "backstory_writing"


@final
@dataclass(frozen=True)
class LlmCallLabel:
    person: PersonId
    name: str
    player_number: int
    being_id: BeingId
    tick: int | None
    purpose: str


# 誰の何の呼び出しかは、LLM を呼ぶスレッドに置く。Being の入口に記録の都合を入れないため (#2321)
_current_label: ContextVar[LlmCallLabel | None] = ContextVar("game_world_llm_call_label", default=None)


def current_label() -> LlmCallLabel | None:
    return _current_label.get()


@contextmanager
def labeled(label: LlmCallLabel) -> Iterator[None]:
    token = _current_label.set(label)
    try:
        yield
    finally:
        _current_label.reset(token)


@final
@dataclass(frozen=True)
class PromptCapture:
    sink: Any
    context: PromptDatasetCallContext


@final
class CountedPromptSink:
    """書けなかった呼び出しは run を止めずに数える。"""

    def __init__(self, inner: PromptDatasetCaptureSink) -> None:
        self._inner = inner
        self._lock = threading.Lock()
        self.recorded = 0
        self.failed = 0

    def record_call(self, **kwargs: Any) -> None:
        try:
            self._inner.record_call(**kwargs)
        except Exception:
            with self._lock:
                self.failed += 1
            _logger.warning("failed to write a game world LLM call to prompt_dataset", exc_info=True)
            return
        with self._lock:
            self.recorded += 1


@final
class LlmCallCapture:
    """LLM のクライアントは組み立てのときに受け取るので、書く先は遊びを始めるときに付ける。"""

    def __init__(self) -> None:
        self._sink: CountedPromptSink | None = None
        self._run_id = ""
        self._lock = threading.Lock()
        self._turns: dict[tuple[PersonId, str], int] = {}

    @property
    def sink(self) -> CountedPromptSink | None:
        return self._sink

    def attach(self, sink: CountedPromptSink, run_id: str) -> None:
        self._sink = sink
        self._run_id = run_id

    def capture(self) -> PromptCapture | None:
        label = current_label()
        if self._sink is None or label is None:
            return None
        with self._lock:
            key = (label.person, label.purpose)
            self._turns[key] = turn = self._turns.get(key, 0) + 1
        return PromptCapture(
            sink=self._sink,
            context=PromptDatasetCallContext(
                llm_call_id=f"llm_{uuid4().hex}",
                run_id=self._run_id,
                world_id=None,
                being_id=label.being_id.value,
                player_id=label.player_number,
                persona_id=label.being_id.value,
                character_name=label.name,
                turn_index=turn,
                world_tick=label.tick,
                phase=label.purpose,
                provenance={"world": "game_world", "person_id": label.person.value, "purpose": label.purpose},
            ),
        )


@final
class CapturedActionChoosing(ActionChoosingCompletion):
    def __init__(self, inner: ActionChoosingCompletion, capture: LlmCallCapture) -> None:
        self._inner = inner
        self._capture = capture

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        if isinstance(self._inner, LiteLLMClient):
            # 生の返事ごと、LiteLLM が呼び出しのあとに書く
            return self._inner.choose_action(
                messages, tools, reasoning_off=reasoning_off, prompt_capture_context=self._capture.capture()
            )
        request = {"model": "stub", "messages": messages, "tools": tools}
        try:
            reply = self._inner.choose_action(messages, tools, reasoning_off=reasoning_off)
        except Exception as error:
            _record(self._capture.capture(), request, error=error, output=None)
            raise
        call = reply.tool_call
        _record(
            self._capture.capture(),
            request,
            error=None,
            output={
                "tool": None if call is None else call.tool_name,
                "arguments": None if call is None else dict(call.arguments),
                "cut_off_while_reasoning": reply.cut_off_while_reasoning,
            },
        )
        return reply


@final
class CapturedEpisodeWriting(EpisodeWritingCompletion):
    def __init__(self, client: LiteLLMClient, capture: LlmCallCapture) -> None:
        self._client = client
        self._capture = capture

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        return self._client.complete_episode_writing_json(messages, prompt_capture_context=self._capture.capture())


def captured_backstory_writing(client: LiteLLMClient, capture: LlmCallCapture) -> Callable[[list[dict[str, str]]], Any]:
    return lambda messages: client.complete_short_term_summary_json(messages, prompt_capture_context=capture.capture())


@final
class LabeledChooseAction:
    """場面を組む本線で人と tick を覚え、考える段 (worker) で LLM を呼ぶあいだだけ、呼び出しに名札を付ける。"""

    def __init__(self, inner: ChooseAction, *, label_for: Callable[[BeingId, str], LlmCallLabel]) -> None:
        self._inner = inner
        self._label_for = label_for
        self._lock = threading.Lock()
        self._labels: dict[int, LlmCallLabel] = {}

    def execute(self, command: ChooseActionCommand) -> ChoiceOutcome:
        return self.settle(self.think(self.prompt(command)))

    def prompt(self, command: ChooseActionCommand) -> ActionPrompt:
        prompt = self._inner.prompt(command)
        label = self._label_for(command.being_id, CHOOSING_ACTION)
        with self._lock:
            self._labels[id(prompt)] = label
        return prompt

    def think(self, prompt: ActionPrompt) -> ActionThought:
        with self._lock:
            label = self._labels.pop(id(prompt))
        with labeled(label):
            return self._inner.think(prompt)

    def settle(self, thought: ActionThought) -> ChoiceOutcome:
        return self._inner.settle(thought)


@final
class LabeledEpisodeWriter(EpisodeWriter):
    def __init__(self, inner: EpisodeWriter, *, label_for: Callable[[Persona, str], LlmCallLabel]) -> None:
        self._inner = inner
        self._label_for = label_for

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        with labeled(self._label_for(persona, WRITING_EPISODES)):
            return self._inner.write(persona=persona, persona_text=persona_text, events_text=events_text)


@final
class LabeledBackstoryWriter(BackstoryWriter):
    def __init__(self, inner: BackstoryWriter, *, label_for: Callable[[Persona, str], LlmCallLabel]) -> None:
        self._inner = inner
        self._label_for = label_for

    def write(
        self,
        *,
        persona: Persona,
        persona_text: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> WrittenBackstory:
        with labeled(self._label_for(persona, WRITING_BACKSTORY)):
            return self._inner.write(
                persona=persona,
                persona_text=persona_text,
                experiences=experiences,
                previous=previous,
                until_turn=until_turn,
                written_turn=written_turn,
            )


def _record(
    capture: PromptCapture | None,
    request: Mapping[str, Any],
    *,
    error: BaseException | None,
    output: Mapping[str, Sequence[Any] | Any] | None,
) -> None:
    if capture is None:
        return
    capture.sink.record_call(context=capture.context, request_kwargs=request, response=None, error=error, output=output)

"""作業記憶と行動の選択肢から、LLM で行動を選ぶ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ai_rpg_world.being.application.action_tools import ActionTools
from ai_rpg_world.being.application.closest_tool_name import unsupported_tool_failure
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.episode_index_revision_tool import (
    EpisodeIndexRevisionOutcome,
    index_revision_call_text,
)
from ai_rpg_world.being.application.episode_recall_tool import recall_call_text
from ai_rpg_world.being.application.memory_writing_in_background import MemoryWritingInBackground
from ai_rpg_world.being.application.names_for_people import name_for
from ai_rpg_world.being.application.own_tool_summary import own_tool_summary
from ai_rpg_world.being.application.recall_episodes import RecallEpisodes, RecallEpisodesCommand
from ai_rpg_world.being.application.rechoose_name import NameRechoice, NamesMatched, RechooseName
from ai_rpg_world.being.application.remember_visited_place import RememberVisitedPlace, RememberVisitedPlaceCommand
from ai_rpg_world.being.application.revise_episode_index import ReviseEpisodeIndex, ReviseEpisodeIndexCommand
from ai_rpg_world.being.application.unwritten_memo_text import unwritten_memo_lines
from ai_rpg_world.being.application.working_memory_text import message_text, system_prompt_text
from ai_rpg_world.being.application.write_memos import WriteMemos, WriteMemosCommand
from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionChoices,
    AgentMove,
    Description,
    FrozenJsonObject,
    Here,
    Observation,
    ObservedTime,
    OfferedBeingTools,
    Orientation,
    OwnActionResult,
    PersonInText,
    Scene,
    TextWithPeople,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.memo_book import MemoBookRepository
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnClock
from ai_rpg_world.being.domain.short_term_memory import (
    MemoryOperationOutcome,
    ObservedOutcome,
    Outcome,
    ShortTermMemoryRepository,
)
from ai_rpg_world.being.domain.visited_places import VisitedPlacesRepository
from ai_rpg_world.being.domain.working_memory import Closing


@dataclass(frozen=True)
class ToolCallReply:
    tool_name: str
    arguments: Mapping[str, object]
    call_id: str | None = None


@dataclass(frozen=True)
class ActionChoosingReply:
    """``cut_off_while_reasoning`` は、考えを有効にした呼び出しが出力の上限で打ち切られたこと。"""

    tool_call: ToolCallReply | None
    cut_off_while_reasoning: bool = False


class ActionChoosingCompletion(ABC):
    @abstractmethod
    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        """呼び出しに失敗したら例外を投げる。"""


@dataclass(frozen=True)
class LlmExchange:
    messages: tuple[dict[str, str], ...]
    tools: tuple[dict[str, Any], ...]
    replies: tuple[ActionChoosingReply, ...]


@dataclass(frozen=True, kw_only=True)
class ChooseActionCommand:
    """``now`` は世界の今の時刻。選べなかったことを、自分の行動の結果として覚えるときに使う。"""

    being_id: BeingId
    orientation: Orientation
    being_tools: OfferedBeingTools
    imposed_goal: str | None
    scene: Scene
    closing: Closing
    choices: ActionChoices
    now: ObservedTime


@dataclass(frozen=True)
class ActionPrompt:
    command: ChooseActionCommand
    tools: ActionTools
    messages: tuple[dict[str, str], ...]
    definitions: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ActionThought:
    prompt: ActionPrompt
    exchange: LlmExchange


@dataclass(frozen=True)
class ActionChosen:
    move: AgentMove
    exchange: LlmExchange
    name_rechoices: tuple[NameRechoice, ...] = ()


@dataclass(frozen=True)
class TurnSpentRecalling:
    """思い出すツールを選んだ。世界には行為を渡さない。"""

    move: AgentMove
    exchange: LlmExchange


@dataclass(frozen=True)
class TurnSpentRevisingIndex:
    """目次を直すツールを選んだ。世界には行為を渡さない。"""

    move: AgentMove
    exchange: LlmExchange
    revision: EpisodeIndexRevisionOutcome


@dataclass(frozen=True)
class ActionNotChosen:
    """``requested_tool`` は出していないツールの名前。ツールを 1 つも呼ばなかったときは None。"""

    requested_tool: str | None
    suggestion: str | None
    exchange: LlmExchange


class ChooseAction:
    """選んだ行動の結果は、世界が返したあとに ``ReceiveActionResult`` で残す。"""

    def __init__(
        self,
        *,
        working_memory: CurrentWorkingMemory,
        completion: ActionChoosingCompletion,
        short_term_memories: ShortTermMemoryRepository,
        turn_clock: MemoryTurnClock,
        memo_books: MemoBookRepository,
        episodes: EpisodeRepository,
        visited_places: VisitedPlacesRepository,
        recall_limit: int,
        rechoose_name: RechooseName | None = None,
        writing_in_background: MemoryWritingInBackground | None = None,
    ) -> None:
        self._recall_episodes = RecallEpisodes(episodes=episodes, recall_limit=recall_limit)
        self._revise_episode_index = ReviseEpisodeIndex(episodes=episodes)
        self._working_memory = working_memory
        self._completion = completion
        self._short_term_memories = short_term_memories
        self._turn_clock = turn_clock
        self._write_memos = WriteMemos(memo_books=memo_books, episodes=episodes)
        self._remember_visited_place = RememberVisitedPlace(visited_places=visited_places)
        self._recall_limit = recall_limit
        self._rechoose_name = rechoose_name
        self._writing_in_background = writing_in_background

    def execute(self, command: ChooseActionCommand) -> ChoiceOutcome:
        return self.settle(self.think(self.prompt(command)))

    def prompt(self, command: ChooseActionCommand) -> ActionPrompt:
        if self._writing_in_background is not None:
            self._writing_in_background.take_in_finished(command.being_id)
        tools = ActionTools(
            command.choices,
            command.being_tools,
            name_for,
            recall_limit=self._recall_limit,
            seen_in_scene=_people_in(command.scene),
        )
        scene = Scene(
            descriptions=(
                *(_named_by(tools, d) for d in command.scene.descriptions),
                *_present(tools.candidate_table()),
            ),
            notices=tuple(_named_by(tools, d) for d in command.scene.notices),
            here=None if command.scene.here is None else _here_named_by(tools, command.scene.here),
        )
        memory = self._working_memory.of(
            command.being_id,
            # 人柄は人ごとに違うので、全員に同じ案内の後ろに置き、案内をプレフィックスのキャッシュに載せる。
            orientation=Orientation(
                (*command.orientation.descriptions, self._working_memory.persona(command.being_id))
            ),
            being_tools=command.being_tools,
            imposed_goal=command.imposed_goal,
            scene=scene,
            closing=command.closing,
        )
        messages = [
            {"role": "system", "content": system_prompt_text(memory)},
            {"role": "user", "content": message_text(memory)},
        ]
        return ActionPrompt(command=command, tools=tools, messages=tuple(messages), definitions=tools.definitions())

    def think(self, prompt: ActionPrompt) -> ActionThought:
        """LLM を呼ぶだけで、記憶には読みも書きもしない。"""
        replies = self._replies(list(prompt.messages), list(prompt.definitions))
        return ActionThought(
            prompt=prompt,
            exchange=LlmExchange(messages=prompt.messages, tools=prompt.definitions, replies=replies),
        )

    def settle(self, thought: ActionThought) -> ChoiceOutcome:
        command = thought.prompt.command
        exchange = thought.exchange
        call = exchange.replies[-1].tool_call
        if call is None:
            return ActionNotChosen(requested_tool=None, suggestion=None, exchange=exchange)
        outcome = self._outcome_of(call, thought.prompt.tools, command, exchange)
        if command.scene.here is not None:
            self._remember_visited_place.execute(
                RememberVisitedPlaceCommand(
                    being_id=command.being_id,
                    environment_name=self._working_memory.environment_name(command.being_id),
                    place=command.scene.here.place,
                )
            )
        return outcome

    def _replies(
        self, messages: list[dict[str, str]], definitions: list[dict[str, Any]]
    ) -> tuple[ActionChoosingReply, ...]:
        # 考えを止めて同じメッセージを送り直せば、キャッシュを崩さずに行動を返させられる。途中までの考えは、
        # 同じ所を回っていることが多く迷いを持ち込むので添えない (design_decisions D1924)。
        first = self._completion.choose_action(messages, definitions, reasoning_off=False)
        if first.tool_call is not None or not first.cut_off_while_reasoning:
            return (first,)
        return (first, self._completion.choose_action(messages, definitions, reasoning_off=True))

    def _outcome_of(
        self, call: ToolCallReply, tools: ActionTools, command: ChooseActionCommand, exchange: LlmExchange
    ) -> ChoiceOutcome:
        turn = _Turn(
            being_id=command.being_id,
            number=self._turn_clock.current_turn(command.being_id) + 1,
            call_id=call.call_id or f"call_{uuid4().hex}",
            call=call,
            command=command,
            exchange=exchange,
        )
        # 2 つに同じ名前を出されたら、前の実装と同じく思い出す方を採る。辞書は後に書いた方が残る。
        routes: dict[str | None, Callable[[_Turn], ChoiceOutcome]] = {
            command.being_tools.episode_index_revision: self._revise,
            command.being_tools.episode_recall: self._recall,
        }
        route = routes.get(call.tool_name)
        if route is not None:
            return route(turn)
        return self._act_on_world(turn, tools)

    def _recall(self, turn: _Turn) -> TurnSpentRecalling:
        recalled = self._recall_episodes.execute(
            RecallEpisodesCommand(being_id=turn.being_id, arguments=turn.call.arguments, turn=turn.number)
        )
        move = turn.own_tool_move()
        self._act(
            turn,
            move,
            call_text=recall_call_text(turn.call.tool_name, turn.call.arguments),
            result=turn.own_tool_outcome(recalled.body, succeeded=recalled.succeeded),
        )
        return TurnSpentRecalling(move=move, exchange=turn.exchange)

    def _revise(self, turn: _Turn) -> TurnSpentRevisingIndex:
        revised = self._revise_episode_index.execute(
            ReviseEpisodeIndexCommand(being_id=turn.being_id, arguments=turn.call.arguments, turn=turn.number)
        )
        move = turn.own_tool_move()
        self._act(
            turn,
            move,
            call_text=index_revision_call_text(turn.call.tool_name, turn.call.arguments),
            result=turn.own_tool_outcome(revised.body, succeeded=revised.succeeded),
        )
        return TurnSpentRevisingIndex(move=move, exchange=turn.exchange, revision=revised.revision)

    def _act_on_world(self, turn: _Turn, tools: ActionTools) -> ActionChosen | ActionNotChosen:
        call = turn.call
        matched = self._names_matched(turn, tools)
        move = tools.move_from(call_id=turn.call_id, tool_name=call.tool_name, arguments=matched.arguments)
        if move is None:
            failure = unsupported_tool_failure(
                requested=call.tool_name,
                valid_tools=tools.tool_names(),
                call_id=turn.call_id,
                now=turn.command.now,
                action_summary=turn.action_summary(),
            )
            self._act(
                turn,
                AgentMove(call_id=turn.call_id, tool_name=call.tool_name, arguments={}),
                result=ObservedOutcome(failure.observation),
            )
            return ActionNotChosen(requested_tool=call.tool_name, suggestion=failure.suggestion, exchange=turn.exchange)
        # 試みより先に書く。試みを残してから書けずに止まると、世界に渡らない試みが結果を待ち続ける。
        # 行動が世界に断られても、書いたことは本人がしたことなので残る。
        memo_rejections = self._write_memo(turn)
        self._act(
            turn,
            move,
            memo_rejections=memo_rejections,
            call_text=tools.call_text(call.tool_name, matched.arguments),
            result=None,
        )
        return ActionChosen(move=move, exchange=turn.exchange, name_rechoices=matched.rechoices)

    def _names_matched(self, turn: _Turn, tools: ActionTools) -> NamesMatched:
        call = turn.call
        if self._rechoose_name is None:
            return NamesMatched(
                arguments=tools.with_names_matched(call.tool_name, call.arguments, lambda *_: None), rechoices=()
            )
        inner_thought = turn.inner_thought()
        return self._rechoose_name.match_names(
            tools, tool_name=call.tool_name, arguments=call.arguments, inner_thought=inner_thought
        )

    def _write_memo(self, turn: _Turn) -> tuple[str, ...]:
        memo = turn.command.being_tools.memo
        if memo is None or memo not in turn.call.arguments:
            return ()
        written = self._write_memos.execute(
            WriteMemosCommand(
                being_id=turn.being_id,
                memo=turn.call.arguments[memo],
                episode_source_offered=turn.command.being_tools.episode_index_shown,
                turn=turn.number,
                environment_name=self._working_memory.environment_name(turn.being_id),
            )
        )
        return unwritten_memo_lines(written.unwritten)

    def _act(
        self,
        turn: _Turn,
        move: AgentMove,
        *,
        result: Outcome | None,
        memo_rejections: tuple[str, ...] = (),
        call_text: str | None = None,
    ) -> None:
        # 保存が済んでから時計を進める。先に進めると、保存に失敗したときにターンの番号が 1 つ飛ぶ。
        memory = self._short_term_memories.get(turn.being_id)
        memory.act(move, current_turn=turn.number, memo_rejections=memo_rejections, call_text=call_text)
        if result is not None:
            memory.receive_result(result, current_turn=turn.number)
        self._short_term_memories.save(memory)
        self._turn_clock.advance_turn(turn.being_id)


def _present(description: Description | None) -> tuple[Description, ...]:
    return () if description is None else (description,)


ChoiceOutcome = ActionChosen | TurnSpentRecalling | TurnSpentRevisingIndex | ActionNotChosen


@dataclass(frozen=True, kw_only=True)
class _Turn:
    being_id: BeingId
    number: int
    call_id: str
    call: ToolCallReply
    command: ChooseActionCommand
    exchange: LlmExchange

    def own_tool_move(self) -> AgentMove:
        return AgentMove(
            call_id=self.call_id, tool_name=self.call.tool_name, arguments=FrozenJsonObject(self.call.arguments)
        )

    def own_tool_outcome(self, body: str, *, succeeded: bool) -> MemoryOperationOutcome:
        return MemoryOperationOutcome(
            call_id=self.call_id,
            body=body,
            time=self.command.now,
            succeeded=succeeded,
            action_summary=self.action_summary(),
        )

    def action_summary(self) -> str:
        tools = self.command.being_tools
        return own_tool_summary(self.call.tool_name, self.call.arguments, hidden=(tools.inner_thought, tools.memo))

    def inner_thought(self) -> str | None:
        name = self.command.being_tools.inner_thought
        thought = self.call.arguments.get(name) if name else None
        return thought if isinstance(thought, str) else None


def _people_in(scene: Scene) -> tuple[PersonInText, ...]:
    texts = (
        *(d.text for d in scene.descriptions),
        *(() if scene.here is None else (scene.here.text,)),
    )
    return tuple(
        person
        for text in texts
        if isinstance(text, TextWithPeople)
        for person in text.people.values()
        if isinstance(person, PersonInText)
    )


def _named_by(tools: ActionTools, description: Description) -> Description:
    text = description.text
    if not isinstance(text, TextWithPeople):
        return description
    return Description(heading=description.heading, text=tools.text_naming_people(text))


def _here_named_by(tools: ActionTools, here: Here) -> Here:
    text = here.text if not isinstance(here.text, TextWithPeople) else tools.text_naming_people(here.text)
    return Here(place=here.place, heading=here.heading, text=text)


__all__ = [
    "ActionChosen",
    "ActionChoosingCompletion",
    "ActionChoosingReply",
    "ActionNotChosen",
    "ActionPrompt",
    "ActionThought",
    "ChooseAction",
    "ChooseActionCommand",
    "LlmExchange",
    "ToolCallReply",
    "TurnSpentRecalling",
    "TurnSpentRevisingIndex",
]

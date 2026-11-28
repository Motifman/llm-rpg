"""作業記憶と行動の選択肢から、LLM で行動を選ぶ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ai_rpg_world.being.application.action_tools import ActionTools
from ai_rpg_world.being.application.closest_tool_name import format_unsupported_tool_message, suggest_closest_tool_name
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.episode_index_revision_tool import (
    HANDLE,
    INDEX_NOT_REVISED_TEXT,
    MALFORMED_INDEX_REVISION_TEXT,
    EpisodeIndexRevisionOutcome,
    index_revised_text,
    index_revision_call_text,
    read_index_revision,
    unknown_handle_text,
)
from ai_rpg_world.being.application.episode_recall_tool import (
    MALFORMED_HANDLES_TEXT,
    read_handles,
    recall_call_text,
    recalled_text,
    too_many_handles_text,
)
from ai_rpg_world.being.application.memory_writing_in_background import MemoryWritingInBackground
from ai_rpg_world.being.application.names_for_people import name_for
from ai_rpg_world.being.application.own_tool_summary import own_tool_summary
from ai_rpg_world.being.application.rechoose_name import NameRechoice, RechooseName
from ai_rpg_world.being.application.unwritten_memo_text import (
    WHOLE_MEMO,
    attempted_raw_operation,
    short_reason,
    unwritten_memo_line,
)
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
    Scene,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.episode_recall import recall_episodes
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
from ai_rpg_world.domain.being.exception.being_exceptions import EpisodeValidationException


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
        if recall_limit < 1:
            raise ValueError("recall_limit must be >= 1")
        self._working_memory = working_memory
        self._completion = completion
        self._short_term_memories = short_term_memories
        self._turn_clock = turn_clock
        self._write_memos = WriteMemos(memo_books=memo_books, episodes=episodes)
        self._episodes = episodes
        self._visited_places = visited_places
        self._recall_limit = recall_limit
        self._rechoose_name = rechoose_name
        self._writing_in_background = writing_in_background

    def execute(
        self, command: ChooseActionCommand
    ) -> ActionChosen | TurnSpentRecalling | TurnSpentRevisingIndex | ActionNotChosen:
        return self.settle(self.think(self.prompt(command)))

    def prompt(self, command: ChooseActionCommand) -> ActionPrompt:
        if self._writing_in_background is not None:
            self._writing_in_background.take_in_finished(command.being_id)
        tools = ActionTools(command.choices, command.being_tools, name_for, recall_limit=self._recall_limit)
        scene = Scene(
            descriptions=(*command.scene.descriptions, *_present(tools.candidate_table())),
            notices=command.scene.notices,
            here=command.scene.here,
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

    def settle(
        self, thought: ActionThought
    ) -> ActionChosen | TurnSpentRecalling | TurnSpentRevisingIndex | ActionNotChosen:
        command = thought.prompt.command
        exchange = thought.exchange
        call = exchange.replies[-1].tool_call
        if call is None:
            return ActionNotChosen(requested_tool=None, suggestion=None, exchange=exchange)
        outcome = self._outcome_of(call, thought.prompt.tools, command, exchange)
        self._visit(command.being_id, command.scene.here)
        return outcome

    def _names_matched(
        self,
        call: ToolCallReply,
        tools: ActionTools,
        being_tools: OfferedBeingTools,
        rechoices: list[NameRechoice],
    ) -> Mapping[str, object]:
        thought = call.arguments.get(being_tools.inner_thought) if being_tools.inner_thought else None

        def rechoose(written: str, label: str, candidates: Mapping[str, str | None], parent: str | None) -> str | None:
            if self._rechoose_name is None:
                return None
            rechoice = self._rechoose_name.rechoose(
                written,
                label=label,
                candidates=candidates,
                parent=parent,
                tool=call.tool_name,
                inner_thought=thought if isinstance(thought, str) else None,
            )
            rechoices.append(rechoice)
            return rechoice.replaced_with

        return tools.with_names_matched(call.tool_name, call.arguments, rechoose)

    def _visit(self, being_id: BeingId, here: Here | None) -> None:
        if here is None:
            return
        places = self._visited_places.get(being_id)
        places.visit(environment_name=self._working_memory.environment_name(being_id), place=here.place)
        self._visited_places.save(places)

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
    ) -> ActionChosen | TurnSpentRecalling | TurnSpentRevisingIndex | ActionNotChosen:
        call_id = call.call_id or f"call_{uuid4().hex}"
        being_id = command.being_id
        turn = self._turn_clock.current_turn(being_id) + 1
        if call.tool_name == command.being_tools.episode_recall:
            recall = AgentMove(call_id=call_id, tool_name=call.tool_name, arguments=FrozenJsonObject(call.arguments))
            body, succeeded = self._recall(being_id, call.arguments, turn=turn)
            self._act(
                being_id,
                recall,
                turn=turn,
                call_text=recall_call_text(call.tool_name, call.arguments),
                result=MemoryOperationOutcome(
                    call_id=call_id,
                    body=body,
                    time=command.now,
                    succeeded=succeeded,
                    action_summary=own_tool_summary(
                        call.tool_name,
                        call.arguments,
                        hidden=(command.being_tools.inner_thought, command.being_tools.memo),
                    ),
                ),
            )
            return TurnSpentRecalling(move=recall, exchange=exchange)
        if call.tool_name == command.being_tools.episode_index_revision:
            revise = AgentMove(call_id=call_id, tool_name=call.tool_name, arguments=FrozenJsonObject(call.arguments))
            body, revision = self._revise(being_id, call.arguments, turn=turn)
            self._act(
                being_id,
                revise,
                turn=turn,
                call_text=index_revision_call_text(call.tool_name, call.arguments),
                result=MemoryOperationOutcome(
                    call_id=call_id,
                    body=body,
                    time=command.now,
                    succeeded=revision.outcome == "revised",
                    action_summary=own_tool_summary(
                        call.tool_name,
                        call.arguments,
                        hidden=(command.being_tools.inner_thought, command.being_tools.memo),
                    ),
                ),
            )
            return TurnSpentRevisingIndex(move=revise, exchange=exchange, revision=revision)
        rechoices: list[NameRechoice] = []
        arguments = self._names_matched(call, tools, command.being_tools, rechoices)
        move = tools.move_from(call_id=call_id, tool_name=call.tool_name, arguments=arguments)
        if move is not None:
            # 試みより先に書く。試みを残してから書けずに止まると、世界に渡らない試みが結果を待ち続ける。
            # 行動が世界に断られても、書いたことは本人がしたことなので残る。
            rejections = self._write_memo(being_id, command.being_tools, call.arguments, turn=turn)
            self._act(
                being_id,
                move,
                turn=turn,
                memo_rejections=rejections,
                call_text=tools.call_text(call.tool_name, arguments),
                result=None,
            )
            return ActionChosen(move=move, exchange=exchange, name_rechoices=tuple(rechoices))
        # 別のツールとして実行すると引数の写し替えが要るので、近い名前を添えて失敗のまま返す (design_decisions #231)。
        suggestion = suggest_closest_tool_name(call.tool_name, tools.tool_names())
        body = format_unsupported_tool_message(
            requested=call.tool_name, valid_tools=tools.tool_names(), suggestion=suggestion
        )
        self._act(
            being_id,
            AgentMove(call_id=call_id, tool_name=call.tool_name, arguments={}),
            turn=turn,
            result=ObservedOutcome(
                _own_failure(
                    body,
                    call_id=call_id,
                    now=command.now,
                    action_summary=own_tool_summary(
                        call.tool_name,
                        call.arguments,
                        hidden=(command.being_tools.inner_thought, command.being_tools.memo),
                    ),
                )
            ),
        )
        return ActionNotChosen(requested_tool=call.tool_name, suggestion=suggestion, exchange=exchange)

    def _recall(self, being_id: BeingId, arguments: Mapping[str, object], *, turn: int) -> tuple[str, bool]:
        """知らない呼び名は、古い run と同じく、思い出せないと答える成功にする。"""
        handles = read_handles(arguments)
        if handles is None:
            return MALFORMED_HANDLES_TEXT, False
        # 一部だけ思い出すと、どれを落としたかを本人が知らないまま 1 手が終わる (D1623-2)。
        if len(set(handles)) > self._recall_limit:
            return too_many_handles_text(self._recall_limit), False
        return recalled_text(recall_episodes(self._episodes, being_id, handles, turn=turn)), True

    def _revise(
        self, being_id: BeingId, arguments: Mapping[str, object], *, turn: int
    ) -> tuple[str, EpisodeIndexRevisionOutcome]:
        handle = arguments.get(HANDLE)
        request = read_index_revision(arguments)
        if request is None:
            return MALFORMED_INDEX_REVISION_TEXT, EpisodeIndexRevisionOutcome(
                handle=handle if isinstance(handle, str) else None, outcome="rejected", reject_reason="malformed"
            )
        episode = self._episodes.find_by_handle(being_id, request.handle)
        if episode is None:
            return unknown_handle_text(request.handle), EpisodeIndexRevisionOutcome(
                handle=request.handle, outcome="rejected", reject_reason="unknown_handle"
            )
        before = episode.index
        try:
            episode.revise_index(request.index, turn=turn)
        except EpisodeValidationException:
            return INDEX_NOT_REVISED_TEXT, EpisodeIndexRevisionOutcome(handle=request.handle, outcome="failed")
        self._episodes.save(episode)
        return index_revised_text(request.handle, request.index), EpisodeIndexRevisionOutcome(
            handle=request.handle,
            outcome="revised",
            before=before,
            after=request.index,
            truncated=request.truncated,
        )

    def _write_memo(
        self, being_id: BeingId, being_tools: OfferedBeingTools, arguments: Mapping[str, object], *, turn: int
    ) -> tuple[str, ...]:
        if being_tools.memo is None or being_tools.memo not in arguments:
            return ()
        written = self._write_memos.execute(
            WriteMemosCommand(
                being_id=being_id,
                memo=arguments[being_tools.memo],
                episode_source_offered=being_tools.episode_index_shown,
                turn=turn,
                environment_name=self._working_memory.environment_name(being_id),
            )
        )
        return tuple(
            unwritten_memo_line(
                WHOLE_MEMO if u.index is None else attempted_raw_operation(u.raw),
                short_reason(u.reason, kind=u.kind),
            )
            for u in sorted(written.unwritten, key=lambda u: -1 if u.index is None else u.index)
        )

    def _act(
        self,
        being_id: BeingId,
        move: AgentMove,
        *,
        turn: int,
        result: Outcome | None,
        memo_rejections: tuple[str, ...] = (),
        call_text: str | None = None,
    ) -> None:
        # 保存が済んでから時計を進める。先に進めると、保存に失敗したときにターンの番号が 1 つ飛ぶ。
        memory = self._short_term_memories.get(being_id)
        memory.act(move, current_turn=turn, memo_rejections=memo_rejections, call_text=call_text)
        if result is not None:
            memory.receive_result(result, current_turn=turn)
        self._short_term_memories.save(memory)
        self._turn_clock.advance_turn(being_id)


def _present(description: Description | None) -> tuple[Description, ...]:
    return () if description is None else (description,)


def _own_failure(body: str, *, call_id: str, now: ObservedTime, action_summary: str) -> Observation:
    return Observation(
        body=body,
        route=OwnActionResult(call_id=call_id, succeeded=False, action_summary=action_summary),
        time=now,
        subject_is_self=True,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=True,
    )


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

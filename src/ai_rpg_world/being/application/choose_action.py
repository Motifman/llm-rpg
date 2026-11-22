"""作業記憶と行動の選択肢から、LLM で行動を選ぶ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ai_rpg_world.being.application.action_tools import ActionTools
from ai_rpg_world.being.application.closest_tool_name import suggest_closest_tool_name
from ai_rpg_world.being.application.current_working_memory import BeingLookup, CurrentWorkingMemory
from ai_rpg_world.being.application.episode_recall_tool import (
    MALFORMED_HANDLES_TEXT,
    read_handles,
    recalled_text,
    too_many_handles_text,
)
from ai_rpg_world.being.application.memo_argument import MEMO_FIELD_NAME
from ai_rpg_world.being.application.memo_arguments import read_memo_operations, rejection_lines, rejection_text
from ai_rpg_world.being.application.memo_writing import apply_memo_operations
from ai_rpg_world.being.application.names_for_people import name_for
from ai_rpg_world.being.application.working_memory_text import message_text, system_prompt_text
from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionChoices,
    AgentMove,
    FrozenJsonObject,
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
from ai_rpg_world.being.domain.working_memory import Closing

RECALL_HEADING = "思い出す"


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
class ActionChosen:
    move: AgentMove
    exchange: LlmExchange


@dataclass(frozen=True)
class TurnSpentRecalling:
    """思い出すツールを選んだ。世界には行為を渡さない。"""

    move: AgentMove
    exchange: LlmExchange


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
        beings: BeingLookup,
        memo_books: MemoBookRepository,
        episodes: EpisodeRepository,
        recall_limit: int,
    ) -> None:
        if recall_limit < 1:
            raise ValueError("recall_limit must be >= 1")
        self._working_memory = working_memory
        self._completion = completion
        self._short_term_memories = short_term_memories
        self._turn_clock = turn_clock
        self._beings = beings
        self._memo_books = memo_books
        self._episodes = episodes
        self._recall_limit = recall_limit

    def execute(self, command: ChooseActionCommand) -> ActionChosen | TurnSpentRecalling | ActionNotChosen:
        tools = ActionTools(command.choices, command.being_tools, name_for, recall_limit=self._recall_limit)
        scene = Scene(
            descriptions=(*command.scene.descriptions, tools.candidate_table()), notices=command.scene.notices
        )
        memory = self._working_memory.of(
            command.being_id,
            orientation=command.orientation,
            being_tools=command.being_tools,
            imposed_goal=command.imposed_goal,
            scene=scene,
            closing=command.closing,
        )
        messages = [
            {"role": "system", "content": system_prompt_text(memory)},
            {"role": "user", "content": message_text(memory)},
        ]
        definitions = list(tools.definitions())
        replies = self._replies(messages, definitions)
        exchange = LlmExchange(messages=tuple(messages), tools=tuple(definitions), replies=replies)
        call = replies[-1].tool_call
        if call is None:
            return ActionNotChosen(requested_tool=None, suggestion=None, exchange=exchange)
        return self._outcome_of(call, tools, command, exchange)

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
    ) -> ActionChosen | TurnSpentRecalling | ActionNotChosen:
        call_id = call.call_id or f"call_{uuid4().hex}"
        being_id = command.being_id
        turn = self._turn_clock.current_turn(being_id) + 1
        if call.tool_name == command.being_tools.episode_recall:
            recall = AgentMove(call_id=call_id, tool_name=call.tool_name, arguments=FrozenJsonObject(call.arguments))
            handles = read_handles(call.arguments)
            self._act(
                being_id,
                recall,
                turn=turn,
                heading=RECALL_HEADING + (f": {' / '.join(handles)}" if handles else ""),
                result=MemoryOperationOutcome(
                    call_id=call_id, body=self._recall(being_id, handles, turn=turn), time=command.now
                ),
            )
            return TurnSpentRecalling(move=recall, exchange=exchange)
        move = tools.move_from(call_id=call_id, tool_name=call.tool_name, arguments=call.arguments)
        heading = tools.action_heading(call.tool_name, call.arguments)
        if move is not None and heading is not None:
            # 試みより先に書く。試みを残してから書けずに止まると、世界に渡らない試みが結果を待ち続ける。
            # 行動が世界に断られても、書いたことは本人がしたことなので残る。
            rejections = self._write_memo(being_id, command.being_tools, call.arguments, turn=turn)
            self._act(being_id, move, turn=turn, heading=heading, memo_rejections=rejections, result=None)
            return ActionChosen(move=move, exchange=exchange)
        # 別のツールとして実行すると引数の写し替えが要るので、近い名前を添えて失敗のまま返す (design_decisions #231)。
        suggestion = suggest_closest_tool_name(call.tool_name, tools.tool_names())
        guess = f"もしかして '{suggestion}' ですか? " if suggestion else ""
        body = f"'{call.tool_name}' というツールは無い。{guess}いま使えるツール: [{', '.join(tools.tool_names())}]"
        self._act(
            being_id,
            AgentMove(call_id=call_id, tool_name=call.tool_name, arguments={}),
            turn=turn,
            heading=call.tool_name,
            result=ObservedOutcome(_own_failure(body, call_id=call_id, now=command.now)),
        )
        return ActionNotChosen(requested_tool=call.tool_name, suggestion=suggestion, exchange=exchange)

    def _recall(self, being_id: BeingId, handles: list[str] | None, *, turn: int) -> str:
        if handles is None:
            return MALFORMED_HANDLES_TEXT
        # 一部だけ思い出すと、どれを落としたかを本人が知らないまま 1 手が終わる (D1623-2)。
        if len(set(handles)) > self._recall_limit:
            return too_many_handles_text(self._recall_limit)
        return recalled_text(recall_episodes(self._episodes, being_id, handles, turn=turn))

    def _write_memo(
        self, being_id: BeingId, being_tools: OfferedBeingTools, arguments: Mapping[str, object], *, turn: int
    ) -> tuple[str, ...]:
        """書けなかった操作の理由を、配列の位置の順に返す。"""
        if being_tools.memo is None or being_tools.memo not in arguments:
            return ()
        episode_source_offered = being_tools.episode_index_shown
        read = read_memo_operations(
            {MEMO_FIELD_NAME: arguments[being_tools.memo]}, episode_source_offered=episode_source_offered
        )
        known_episode_handles = (
            frozenset(e.handle for e in self._episodes.list_by_being(being_id))
            if episode_source_offered
            else frozenset()
        )
        book = self._memo_books.get(being_id)
        outcome = apply_memo_operations(
            book,
            read.operations,
            turn=turn,
            environment_name=self._environment_name(being_id),
            new_memo_id=lambda: str(uuid4()),
            known_episode_handles=known_episode_handles,
        )
        self._memo_books.save(book)
        rejected = [(r.index, rejection_text(r.reason)) for r in read.rejected] + [
            (r.index, rejection_text(r.reason, kind=r.kind, detail=r.detail)) for r in outcome.rejected
        ]
        return rejection_lines(sorted(rejected, key=lambda r: -1 if r[0] is None else r[0]))

    def _environment_name(self, being_id: BeingId) -> str:
        being = self._beings.find_by_id(being_id)
        if being is None or being.attachment is None:
            raise LookupError(f"Being {being_id.value} is not in any environment")
        return being.attachment.environment_name

    def _act(
        self,
        being_id: BeingId,
        move: AgentMove,
        *,
        turn: int,
        heading: str,
        result: Outcome | None,
        memo_rejections: tuple[str, ...] = (),
    ) -> None:
        # 保存が済んでから時計を進める。先に進めると、保存に失敗したときにターンの番号が 1 つ飛ぶ。
        memory = self._short_term_memories.get(being_id)
        memory.act(move, current_turn=turn, action_heading=heading, memo_rejections=memo_rejections)
        if result is not None:
            memory.receive_result(result, current_turn=turn)
        self._short_term_memories.save(memory)
        self._turn_clock.advance_turn(being_id)


def _own_failure(body: str, *, call_id: str, now: ObservedTime) -> Observation:
    return Observation(
        body=body,
        route=OwnActionResult(call_id=call_id, succeeded=False),
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
    "ChooseAction",
    "ChooseActionCommand",
    "LlmExchange",
    "ToolCallReply",
    "TurnSpentRecalling",
]

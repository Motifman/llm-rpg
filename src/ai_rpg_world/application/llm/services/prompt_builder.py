"""1 ターン分のプロンプトを、Being の作業記憶 (#1630) から組む。"""

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
        ToolCallLoopGuardService,
    )
from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    PromptBuilderCoreServices,
    PromptLimits,
    PromptSectionProviders,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.llm.services.world_scene import (
    CURRENT_SURROUNDINGS_HEADING,
    current_surroundings_description,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.working_memory_text import closing_text, message_text, system_prompt_text
from ai_rpg_world.being.contract import Description, Scene
from ai_rpg_world.being.domain.working_memory import (
    BACKSTORY_HEADING,
    EPISODE_INDEX_HEADING,
    GOAL_HEADING,
    KNOWN_PEOPLE_HEADING,
    MEMO_HEADING,
    RECENT_EVENTS_HEADING,
    Closing,
    WorkingMemory,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
MESSAGE_WHEN_PLAYER_NOT_PLACED = "現在地: 未配置。ゲームに参加するまで待機しています。"


class DefaultPromptBuilder(IPromptBuilder):
    """観測バッファから取り出した観測を短期記憶へ足し、環境の材料 (案内、場面、目的、締め) を集めて、
    Being の作業記憶から文を組む。区画の中身と並びは作業記憶が決める。
    """

    def __init__(
        self,
        core: PromptBuilderCoreServices,
        *,
        sections: PromptSectionProviders | None = None,
        limits: PromptLimits | None = None,
        ui_context_builder: ILlmUiContextBuilder,
        current_tick_provider: Callable[[], int | None] | None = None,
        trace_recorder: Optional["ITraceRecorder"] = None,
        trace_recorder_provider: Callable[[], Optional["ITraceRecorder"]] | None = None,
        tool_call_loop_guard: Optional["ToolCallLoopGuardService"] = None,
    ) -> None:
        sections = sections or PromptSectionProviders()
        limits = limits or PromptLimits()
        if not isinstance(core, PromptBuilderCoreServices):
            raise TypeError("core must be PromptBuilderCoreServices")
        if not isinstance(sections, PromptSectionProviders):
            raise TypeError("sections must be PromptSectionProviders")
        if not isinstance(limits, PromptLimits):
            raise TypeError("limits must be PromptLimits")
        # world_query_service は「呼ぶ 1 メソッドを満たせばよい」duck-type 契約 (Issue #227 HIGH-3 Part 2)。
        if not hasattr(core.world_query_service, "get_player_current_state"):
            raise TypeError("core.world_query_service must have get_player_current_state method")
        if not isinstance(core.observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(core.recent_event_store, UnifiedRecentEventStore):
            raise TypeError("recent_event_store must be UnifiedRecentEventStore")
        if not isinstance(core.current_state_formatter, ICurrentStateFormatter):
            raise TypeError("current_state_formatter must be ICurrentStateFormatter")
        if not isinstance(core.available_tools_provider, IAvailableToolsProvider):
            raise TypeError("available_tools_provider must be IAvailableToolsProvider")
        if not isinstance(core.working_memory, CurrentWorkingMemory):
            raise TypeError("working_memory must be CurrentWorkingMemory")
        if not callable(core.orientation_provider):
            raise TypeError("orientation_provider must be callable")
        if not callable(core.conduct_text_provider):
            raise TypeError("conduct_text_provider must be callable")
        if not isinstance(ui_context_builder, ILlmUiContextBuilder):
            raise TypeError("ui_context_builder must be ILlmUiContextBuilder")
        if not isinstance(limits.default_action_instruction, str):
            raise TypeError("default_action_instruction must be str")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        if sections.objective_text_provider is not None and not callable(sections.objective_text_provider):
            raise TypeError("objective_text_provider must be callable or None")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")

        # 直前ターンで同じ tool + 同じ引数を選ぼうとしているとき、その状態を
        # peek して締めの一文の前に専用警告を挟む (= attention 補強)。
        # loop_guard 本体の observation 注入は recent_events に並ぶので
        # 埋もれやすい。recency bias が効きやすい末尾に置いて、LLM が「直前と同じ手」を
        # 選ぶ直前にもう一度気付くきっかけを作る。None なら警告は出ない。
        if tool_call_loop_guard is not None:
            from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
                ToolCallLoopGuardService,
            )

            if not isinstance(tool_call_loop_guard, ToolCallLoopGuardService):
                raise TypeError("tool_call_loop_guard must be ToolCallLoopGuardService or None")
        self._tool_call_loop_guard = tool_call_loop_guard
        self._objective_text_provider = sections.objective_text_provider
        self._current_tick_provider = current_tick_provider
        self._observation_buffer = core.observation_buffer
        self._recent_event_store = core.recent_event_store
        self._world_query_service = core.world_query_service
        self._current_state_formatter = core.current_state_formatter
        self._available_tools_provider = core.available_tools_provider
        self._working_memory = core.working_memory
        self._orientation_provider = core.orientation_provider
        self._conduct_text_provider = core.conduct_text_provider
        self._ui_context_builder = ui_context_builder
        self._default_action_instruction = limits.default_action_instruction
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._logger = logging.getLogger(self.__class__.__name__)

    def _resolve_trace_recorder(self) -> ITraceRecorder | None:
        """trace の recorder を runtime 時点で取得する。

        ``trace_recorder_provider`` があれば毎回 lookup (= 後付け差し込み
        対応)、なければ構築時固定値。provider 例外は None フォールバック
        (= prompt は普段通り組まれ、trace 行だけ落ちる)。
        """
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                # 通常 provider は単純な lambda なので例外は希。DI 化や
                # 動的解決を加えたときに silent に消えるのを防ぐため DEBUG
                # 級で痕跡を残す。
                self._logger.debug(
                    "trace_recorder_provider raised; skipping trace",
                    exc_info=True,
                )
                return None
        return self._trace_recorder

    def _emit_prompt_section_breakdown_trace(
        self,
        *,
        player_id: PlayerId,
        memory: WorkingMemory,
        system_content: str,
        user_content: str,
        tools: list[dict[str, Any]],
    ) -> None:
        """``PROMPT_SECTION_BREAKDOWN`` を 1 件記録する (失敗は握りつぶす)。

        区画ごとの文字数は、作業記憶の区画の本文 (見出しの行を除く) から数える。無い区画は 0。
        後続の prefix cache / token 分析で「どの区画が prompt_tokens を支配しているか」が分かる。
        tools 配列は ``json.dumps`` でシリアライズした長さを使う。
        """
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: int | None = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            import json as _json

            tools_chars = len(_json.dumps(tools, ensure_ascii=False))
        except Exception:
            tools_chars = 0

        def chars(heading: str) -> int:
            section = memory.section(heading)
            return len("\n".join(section.lines)) if section is not None else 0

        try:
            recorder.record(
                TraceEventKind.PROMPT_SECTION_BREAKDOWN,
                tick=tick,
                player_id=int(player_id.value),
                system_chars=len(system_content),
                objective_chars=chars(GOAL_HEADING),
                known_people_chars=chars(KNOWN_PEOPLE_HEADING),
                episode_index_chars=chars(EPISODE_INDEX_HEADING),
                current_state_chars=chars(CURRENT_SURROUNDINGS_HEADING),
                memos_chars=chars(MEMO_HEADING),
                recent_events_chars=chars(RECENT_EVENTS_HEADING),
                backstory_chars=chars(BACKSTORY_HEADING),
                instruction_chars=len(closing_text(memory)),
                tools_chars=tools_chars,
                user_content_chars=len(user_content),
                messages_total_chars=len(system_content) + len(user_content),
                tools_count=len(tools),
            )
        except Exception:
            self._logger.debug(
                "trace recorder.record raised for PROMPT_SECTION_BREAKDOWN; skipping",
                exc_info=True,
            )

    def _build_loop_warning_prefix(self, player_id: PlayerId) -> str:
        """instruction の前に挟む「同じ手の繰り返し」警告 prefix を返す。

        ``tool_call_loop_guard.peek_streak`` が連続 2 回以上を返したときだけ
        prefix を作る。それ以外は空文字。文面は recent_events に流れる
        loop_guard 警告と意図的に重ねて、両方の attention 経路を踏む。
        """
        if self._tool_call_loop_guard is None:
            return ""
        try:
            streak = self._tool_call_loop_guard.peek_streak(player_id)
        except Exception:
            return ""
        if streak is None:
            return ""
        tool_name, count = streak
        return (
            f"⚠ 直前のあなたは `{tool_name}` を同じ引数で {count} ターン連続"
            f"実行しました。同じ手を取れば同じ結果しか返りません。"
            f"「直近の出来事」のエラーメッセージや状況のヒントを読み返し、"
            f"別の選択肢 (引数を変える / 別のツールを使う / 周囲に尋ねる等) "
            f"を選んでください。"
        )

    def build(
        self,
        acting: ActingBeing,
        action_instruction: str | None = None,
        notices: Sequence[Description] = (),
    ) -> dict[str, Any]:
        """作業記憶 (#1630) を組み、システムプロンプトとメッセージの文にする。

        ``notices`` は場面に付く知らせ (進行中の異常、時間の経過など)。
        """
        if not isinstance(acting, ActingBeing):
            raise TypeError("acting must be ActingBeing")
        if action_instruction is not None and not isinstance(action_instruction, str):
            raise TypeError("action_instruction must be str or None")
        player_id = acting.player_id
        orientation = self._orientation_provider(player_id)
        if orientation is None:
            raise PlayerProfileNotFoundForPromptException(player_id.value)

        # 預かった観測を取り出して足す。足すと写す処理が Being の短期記憶に書く。
        for entry in self._observation_buffer.drain(player_id):
            self._recent_event_store.append_observation(player_id, entry)

        current_state_dto = self._world_query_service.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=player_id.value)
        )
        if current_state_dto is not None:
            base_current_state_text = self._current_state_formatter.format(current_state_dto)
        else:
            base_current_state_text = MESSAGE_WHEN_PLAYER_NOT_PLACED
        ui_context = self._ui_context_builder.build(base_current_state_text, current_state_dto)
        current_state_text = ui_context.current_state_text
        tools = self._available_tools_provider.get_available_tools(current_state_dto)
        objective_text = self._call_text_provider(self._objective_text_provider, player_id, "objective_text_provider")

        instruction = action_instruction or self._default_action_instruction
        loop_warning = self._build_loop_warning_prefix(player_id) or None
        scene = Scene((current_surroundings_description(current_state_text),), notices=notices)
        memory = self._working_memory.of(
            acting.being_id,
            orientation=orientation,
            conduct=self._conduct_text_provider(),
            imposed_goal=objective_text,
            scene=scene,
            closing=Closing(instruction=instruction, warning=loop_warning),
        )
        system_content = system_prompt_text(memory)
        user_content = message_text(memory)

        result: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "tools": tools,
            "tool_choice": "required",
            "tool_runtime_context": ui_context.tool_runtime_context,
            # Phase A が、実際に API へ出す tool 集合から動的引数候補表を作り、
            # この指示の直前へ差し込むための境界。区画より後ろの文 (警告、知らせ、締め) にあたる。
            "action_instruction": closing_text(memory),
            "current_state_snapshot": current_state_text,
            "working_memory": memory,
            "scene": scene,
        }
        self._emit_prompt_section_breakdown_trace(
            player_id=player_id,
            memory=memory,
            system_content=system_content,
            user_content=user_content,
            tools=tools,
        )
        return result

    def _call_text_provider(
        self,
        provider: Callable[[PlayerId], str] | None,
        player_id: PlayerId,
        provider_name: str,
    ) -> str:
        """provider を呼んで text を返す。落ちたら ERROR ログ + 空文字 degrade。

        provider バグを silent に握り潰すと debug が極めて困難になるため、
        ERROR レベル + exc_info=True でログ集約側に必ず可視化させる。
        prompt 構築自体は止めず degrade で続行する (provider は補助的な
        section なので、欠けても LLM ターン自体は成立する)。
        """
        if provider is None:
            return ""
        try:
            return provider(player_id) or ""
        except Exception:
            self._logger.error(
                "%s raised; degrading to empty text. Fix provider implementation.",
                provider_name,
                exc_info=True,
            )
            return ""

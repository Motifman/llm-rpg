"""
LLM エージェントの 1 ターン実行を統合するオーケストレータ。

プロンプト組み立て → LLM 呼び出し → tool_call 取得 → コマンド実行 → 結果を IActionResultStore に記録。
"""

import json
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    is_reschedulable_error_code,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IPromptBuilder,
    IToolArgumentResolver,
)
from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.result_summary_builder import build_result_summary
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    SUBJECTIVE_ACTION_TEXT_FIELDS,
    is_subjective_action_tool,
)
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.trace import (
    ITraceRecorder,
    NullTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)

# memo 系ツール (todo_* alias と同じ文字列) の実行時は hint を出さない:
# memo_done を呼んだ直後にさらに hint を出すと冗長で、memo_add / memo_list 中も
# memo 内容に対する augment は意味がない (LLM が能動的に memo を操作している場面)
_MEMO_TOOLS_SKIPPING_HINT: frozenset[str] = frozenset(
    {TOOL_NAME_TODO_ADD, TOOL_NAME_TODO_LIST, TOOL_NAME_TODO_COMPLETE}
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOOLS_SKIPPING_EPISODIC_CHUNK: frozenset[str] = frozenset(
    {
        TOOL_NAME_TODO_ADD,
        TOOL_NAME_TODO_LIST,
        TOOL_NAME_TODO_COMPLETE,
        TOOL_NAME_MEMORY_EXPLORE_RELATED,
    }
)


def _format_action_summary(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    """ツール名と引数から「直近の出来事」用の行動要約文を組み立てる。"""
    if not arguments:
        return f"{tool_name} を実行しました。"
    try:
        args_str = json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        args_str = str(arguments)
    return f"{tool_name}({args_str}) を実行しました。"


def _append_to_action_store(
    store: IActionResultStore,
    player_id: PlayerId,
    result_dto: LlmCommandResultDto,
    action_summary: str,
    result_summary: str,
    *,
    tool_name: Optional[str] = None,
    fingerprint_args: Optional[Dict[str, Any]] = None,
    game_time_label: Optional[str] = None,
) -> None:
    """行動結果を IActionResultStore に記録する（失敗メタ・引数フィンガープリント付き）。

    Issue #188 改善:
    - ``result_dto.omit_result_in_prompt`` を store にそのまま伝える
      (formatter が成功時の result_summary を省略するかの判断材料)
    - ``game_time_label`` を store に渡し、観測と対称な時刻表示を可能に
    """
    fp = build_argument_fingerprint(fingerprint_args) if fingerprint_args is not None else None
    store.append(
        player_id,
        action_summary,
        result_summary,
        success=result_dto.success,
        error_code=result_dto.error_code,
        tool_name=tool_name,
        argument_fingerprint=fp,
        should_reschedule=result_dto.should_reschedule,
        game_time_label=game_time_label,
        omit_result_in_prompt=result_dto.omit_result_in_prompt,
    )


def _validate_subjective_action_arguments(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Optional[LlmCommandResultDto]:
    """世界へ作用する tool の主観入力を hard validation する。"""
    if not is_subjective_action_tool(tool_name):
        return None

    for field_name in SUBJECTIVE_ACTION_TEXT_FIELDS:
        raw = arguments.get(field_name)
        if not isinstance(raw, str) or not raw.strip():
            return LlmCommandResultDto(
                success=False,
                message=f"{field_name} は必須です。空でない文字列を指定してください。",
                error_code="MISSING_SUBJECTIVE_ACTION_FIELD",
                remediation=(
                    "世界へ作用する tool では inner_thought / intention / "
                    "expected_result / attention / emotion_hint を必ず指定してください。"
                ),
                should_reschedule=True,
            )

    emotion = arguments.get("emotion_hint")
    if not isinstance(emotion, str) or emotion not in EMOTION_HINT_VALUES:
        return LlmCommandResultDto(
            success=False,
            message="emotion_hint は定義済み enum のいずれかを指定してください。",
            error_code="INVALID_EMOTION_HINT",
            remediation=(
                "emotion_hint は curiosity / caution / fear / anxiety / urgency / "
                "relief / hope / frustration / confusion / trust / distrust / "
                "determination / regret / surprise / neutral から 1 つ選んでください。"
            ),
            should_reschedule=True,
        )

    return None


class LlmAgentOrchestrator:
    """
    1 ターン分の流れ: プロンプト build → LLM 呼び出し → tool_call に従いコマンド実行
    → 結果を IActionResultStore に append。
    """

    def __init__(
        self,
        prompt_builder: IPromptBuilder,
        llm_client: ILLMClient,
        tool_command_mapper: ToolCommandMapper,
        action_result_store: IActionResultStore,
        tool_argument_resolver: Optional[IToolArgumentResolver] = None,
        episodic_chunk_coordinator: Optional[EpisodicChunkCoordinator] = None,
        episodic_reinterpretation_coordinator: Optional[EpisodicReinterpretationCoordinator] = None,
        episodic_semantic_promotion: Optional[EpisodicSemanticClusterPromotionService] = None,
        game_time_label_provider: Optional[Callable[[], Optional[str]]] = None,
        memo_completion_hint_service: Optional[MemoCompletionHintService] = None,
        trace_recorder: Optional[ITraceRecorder] = None,
        tick_provider: Optional[Callable[[], Optional[int]]] = None,
        tool_call_loop_guard: Optional[ToolCallLoopGuardService] = None,
    ) -> None:
        if not isinstance(prompt_builder, IPromptBuilder):
            raise TypeError("prompt_builder must be IPromptBuilder")
        if not isinstance(llm_client, ILLMClient):
            raise TypeError("llm_client must be ILLMClient")
        if not isinstance(tool_command_mapper, ToolCommandMapper):
            raise TypeError("tool_command_mapper must be ToolCommandMapper")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if tool_argument_resolver is not None and not isinstance(
            tool_argument_resolver, IToolArgumentResolver
        ):
            raise TypeError(
                "tool_argument_resolver must be IToolArgumentResolver or None"
            )
        if episodic_chunk_coordinator is not None and not isinstance(
            episodic_chunk_coordinator, EpisodicChunkCoordinator
        ):
            raise TypeError(
                "episodic_chunk_coordinator must be EpisodicChunkCoordinator or None"
            )
        if episodic_reinterpretation_coordinator is not None and not isinstance(
            episodic_reinterpretation_coordinator,
            EpisodicReinterpretationCoordinator,
        ):
            raise TypeError(
                "episodic_reinterpretation_coordinator must be "
                "EpisodicReinterpretationCoordinator or None"
            )
        if episodic_semantic_promotion is not None and not isinstance(
            episodic_semantic_promotion, EpisodicSemanticClusterPromotionService
        ):
            raise TypeError(
                "episodic_semantic_promotion must be EpisodicSemanticClusterPromotionService or None"
            )
        if game_time_label_provider is not None and not callable(
            game_time_label_provider
        ):
            raise TypeError(
                "game_time_label_provider must be Callable[[], Optional[str]] or None"
            )
        if memo_completion_hint_service is not None and not isinstance(
            memo_completion_hint_service, MemoCompletionHintService
        ):
            raise TypeError(
                "memo_completion_hint_service must be MemoCompletionHintService or None"
            )
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if tick_provider is not None and not callable(tick_provider):
            raise TypeError("tick_provider must be Callable[[], Optional[int]] or None")
        if tool_call_loop_guard is not None and not isinstance(
            tool_call_loop_guard, ToolCallLoopGuardService
        ):
            raise TypeError(
                "tool_call_loop_guard must be ToolCallLoopGuardService or None"
            )
        self._game_time_label_provider = game_time_label_provider
        self._memo_completion_hint_service = memo_completion_hint_service
        self._trace_recorder: ITraceRecorder = trace_recorder or NullTraceRecorder()
        self._tick_provider = tick_provider
        self._prompt_builder = prompt_builder
        self._llm_client = llm_client
        self._tool_command_mapper = tool_command_mapper
        self._action_result_store = action_result_store
        self._tool_argument_resolver = (
            tool_argument_resolver
            if tool_argument_resolver is not None
            else DefaultToolArgumentResolver()
        )
        self._episodic_chunk_coordinator = episodic_chunk_coordinator
        self._episodic_reinterpretation_coordinator = episodic_reinterpretation_coordinator
        self._episodic_semantic_promotion = episodic_semantic_promotion
        self._tool_call_loop_guard = tool_call_loop_guard

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        """
        1 ターン実行: プロンプト組み立て → LLM 呼び出し → tool_call を実行 → 結果を store に記録。
        戻り値はそのターンの実行結果（LlmCommandResultDto）。
        tool_call が無い場合は「ツール未選択」として store に記録し、対応する DTO を返す。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")

        try:
            return self._run_turn_core(player_id)
        finally:
            if self._episodic_reinterpretation_coordinator is not None:
                self._episodic_reinterpretation_coordinator.after_turn_completed(player_id)

    def _current_tick(self) -> Optional[int]:
        """trace event に載せる現在 tick を取得 (provider 未設定なら None)。"""
        if self._tick_provider is None:
            return None
        try:
            return self._tick_provider()
        except Exception:
            return None

    def _maybe_augment_with_memo_hint(
        self,
        player_id: PlayerId,
        tool_name: str,
        action_summary: str,
        result_summary: str,
    ) -> str:
        """Issue #188 Phase 1c: memo 完了 hint を result_summary に付与する。

        memo_* ツールの実行直後は hint を出さない (冗長 / 自己参照ループ防止)。
        service が未注入なら無加工で返す。

        Issue #240 後続: hint が発火したら trace に MEMO_HINT イベントを emit
        し、実 LLM 試走で「hint が出たか / それを見て LLM が memo_done したか」
        が追えるようにする。
        """
        if self._memo_completion_hint_service is None:
            return result_summary
        if tool_name in _MEMO_TOOLS_SKIPPING_HINT:
            return result_summary
        try:
            hint = self._memo_completion_hint_service.detect(
                player_id, action_summary, result_summary
            )
        except Exception:
            # detect 失敗で本体パイプラインを壊さない
            return result_summary

        if hint is None:
            return result_summary

        # trace に MEMO_HINT イベントを emit (silent except: trace 失敗で本体を止めない)
        try:
            self._trace_recorder.record(
                TraceEventKind.MEMO_HINT,
                tick=self._current_tick(),
                player_id=player_id.value,
                memo_id=hint.memo.id,
                memo_content=hint.memo.content,
                similarity=round(hint.similarity, 4),
                tool_name=tool_name,
            )
        except Exception:
            pass

        return result_summary + hint.to_hint_text()

    def _run_turn_core(self, player_id: PlayerId) -> LlmCommandResultDto:
        request = self._prompt_builder.build(player_id)
        messages = request["messages"]
        tools = request["tools"]
        tool_choice = request.get("tool_choice", "required")
        runtime_context = request.get("tool_runtime_context")
        if not isinstance(runtime_context, ToolRuntimeContextDto):
            runtime_context = ToolRuntimeContextDto.empty()

        # Issue #188: 行動結果にも観測と対称な game_time_label を付与する。
        # provider が注入されていれば毎ターンの先頭で 1 度引いて、本ターン中の
        # 全 _append_to_action_store 呼び出しで同一ラベルを共有する。
        time_label = (
            self._game_time_label_provider()
            if self._game_time_label_provider is not None
            else None
        )

        try:
            tool_call = self._llm_client.invoke(messages, tools, tool_choice)
        except LlmApiCallException as e:
            action_summary = "LLM API 呼び出しに失敗しました。"
            result_dto = LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=e.error_code,
                remediation=get_remediation(e.error_code),
                should_reschedule=is_reschedulable_error_code(e.error_code),
            )
            result_summary = build_result_summary(result_dto)
            _append_to_action_store(
                self._action_result_store,
                player_id,
                result_dto,
                action_summary,
                result_summary,
                game_time_label=time_label,
            )
            return result_dto

        if tool_call is None:
            action_summary = "ツールが選択されませんでした。"
            result_dto = LlmCommandResultDto(
                success=False,
                message="LLM がツールを返しませんでした。",
                error_code="NO_TOOL_CALL",
                remediation="必ずいずれか 1 つのツールを呼び出してください。",
                should_reschedule=True,
            )
            result_summary = build_result_summary(result_dto)
            _append_to_action_store(
                self._action_result_store,
                player_id,
                result_dto,
                action_summary,
                result_summary,
                game_time_label=time_label,
            )
            return result_dto

        name = tool_call.get("name", "")
        raw_args = tool_call.get("arguments")
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = raw_args if isinstance(raw_args, dict) else {}

        validation_error = _validate_subjective_action_arguments(name, arguments)
        if validation_error is not None:
            action_summary = _format_action_summary(name, arguments)
            result_summary = build_result_summary(validation_error)
            _append_to_action_store(
                self._action_result_store,
                player_id,
                validation_error,
                action_summary,
                result_summary,
                tool_name=name or None,
                fingerprint_args=arguments,
                game_time_label=time_label,
            )
            return validation_error

        try:
            canonical_arguments = self._tool_argument_resolver.resolve(
                name,
                arguments,
                runtime_context,
            )
        except ToolArgumentResolutionException as e:
            result_dto = LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=e.error_code,
                remediation=get_remediation(e.error_code),
                should_reschedule=is_reschedulable_error_code(e.error_code),
            )
            action_summary = _format_action_summary(name, arguments)
            result_summary = build_result_summary(result_dto)
            _append_to_action_store(
                self._action_result_store,
                player_id,
                result_dto,
                action_summary,
                result_summary,
                tool_name=name or None,
                fingerprint_args=arguments,
                game_time_label=time_label,
            )
            return result_dto

        current_tick = self._current_tick()
        self._trace_recorder.record(
            TraceEventKind.ACTION,
            tick=current_tick,
            player_id=player_id.value,
            tool=name,
            arguments=arguments,
        )
        result_dto = self._tool_command_mapper.execute(
            player_id.value,
            name,
            canonical_arguments,
        )
        action_summary = _format_action_summary(name, arguments)
        result_summary = build_result_summary(result_dto)
        result_summary = self._maybe_augment_with_memo_hint(
            player_id, name, action_summary, result_summary
        )
        self._trace_recorder.record(
            TraceEventKind.ACTION_RESULT,
            tick=current_tick,
            player_id=player_id.value,
            tool=name,
            success=result_dto.success,
            error_code=result_dto.error_code,
            result_summary=result_summary,
        )
        _append_to_action_store(
            self._action_result_store,
            player_id,
            result_dto,
            action_summary,
            result_summary,
            tool_name=name or None,
            fingerprint_args=canonical_arguments,
            game_time_label=time_label,
        )
        if self._tool_call_loop_guard is not None and name:
            # action_result_store への記録成功後に loop guard を回す。
            # 連打が検知された場合は次ターンの観測として警告が注入される。
            self._tool_call_loop_guard.record_and_check(
                player_id,
                name,
                canonical_arguments,
                game_time_label=time_label,
            )
        if self._episodic_chunk_coordinator is not None and name not in _TOOLS_SKIPPING_EPISODIC_CHUNK:
            # 既定は False。True に固定すると毎ツール成功のたびに即セグメント閉鎖となり、
            # chunk_boundary（観測ヒント等）による HOLD が実質使えなくなるため。
            self._episodic_chunk_coordinator.after_action_recorded(
                player_id,
                explicit_segment_close=False,
            )
        if self._episodic_semantic_promotion is not None:
            self._episodic_semantic_promotion.on_after_tool_turn(player_id.value)
        return result_dto

"""Session-local LLM loop wiring for the world runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import IntentIdGenerator
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    TOOL_NAME_MEMORY_RECALL_EPISODES,
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
    TOOL_NAME_SPEECH,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)

from ai_rpg_world.application.llm.services.world_llm_turn.phase_a import (
    action_failure_key,
    build_tools_payload,
    parse_assessment_tool_call,
    run_phase_a,
)
from ai_rpg_world.application.llm.services.world_llm_turn.phase_b import run_phase_b
from ai_rpg_world.application.llm.services.world_llm_turn.prompt_capture import (
    llm_session_id,
    llm_session_kwargs,
)
from ai_rpg_world.application.llm.services.world_llm_turn.speech_handler import (
    handle_speech,
    resolve_whisper_target,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    BUSY_FREE_TOOLS,
    adapt_executor_handler_with_resolver,
    build_interact_invalid_label_failure,
    build_travel_to_invalid_label_failure,
    coerce_arguments,
    definitions_across_phases,
    execute_tool,
    make_auxiliary_tool_handler,
    maybe_interrupt_busy,
    reason_tool_is_not_offered,
    restore_nav_state,
    validate_tool_handler_consistency_for_wiring,
    wire_missing_spot_graph_tools,
)
from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    WorldLlmTurnTrigger,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult

logger = logging.getLogger(__name__)


@dataclass
class WorldLlmWiring:
    """Session-local LLM loop for the world runtime.

    **Two-phase construction invariant**:
    ``action_failed_emitter`` と ``intent_id_generator`` は ``ObservationTurnScheduler``
    → ``ActionFailedObservationEmitter`` の構築連鎖が ``llm_turn_trigger`` を
    必要とするため、本クラスの ``__init__`` 直後に注入する必要がある。
    ``create_session`` の流れは:

        1. ``WorldLlmWiring(...)`` を ctor で作成 (内部で trigger 生成)
        2. ``ObservationTurnScheduler`` を trigger を使って組み立て
        3. ``ActionFailedObservationEmitter`` を scheduler を使って組み立て
        4. ``attach_action_failed_wiring(emitter, generator)`` を呼ぶ
        5. ``self._sessions[sid]`` に登録 (これ以降 tick loop から見える)

    手順 4 を踏まずに 5 に到達すると、失敗 DTO が出ても観測化されない silent
    bug になる。アサーションで防げないため (Optional として動かす設計)、本
    docstring の手順を守ること。
    """

    runtime: Any
    observation_buffer: Any
    short_term_memory: IShortTermMemory
    llm_client: Any = field(default_factory=StubLlmClient)
    llm_session_run_id: str = "interactive"
    llm_session_world_id: str = "world"
    prompt_dataset_sink: Optional[Any] = None
    max_self_reschedule_streak: int = 5
    action_failed_emitter: Optional[ActionFailedObservationEmitter] = None
    intent_id_generator: Optional[IntentIdGenerator] = None

    _BUSY_FREE_TOOLS = BUSY_FREE_TOOLS

    def __post_init__(self) -> None:
        self.observation_appender = ObservationAppender(self.observation_buffer)
        self.llm_turn_trigger = WorldLlmTurnTrigger(
            wiring=self,
            max_self_reschedule_streak=self.max_self_reschedule_streak,
        )
        # PR 4 (#227): 同一ツール連打を engine 側で検知し、警告を観測として
        # 注入する loop guard。PR #230 で LlmAgentOrchestrator 経由で配線
        # していたが、world_runtime の独自 turn 実行はそれを経由しないため、
        # ここで wiring に直接組み込む。閾値は ToolCallLoopGuardService の
        # 既定値 (wait=3 / travel_to=2 / interact=4 / その他=5) を使う。
        # Issue #240 後続: trace_recorder + current_tick_provider を注入し、
        # loop_guard 警告が trace.jsonl に LOOP_GUARD_WARNING として残るようにする。
        # 第15回実験で「警告は出てるはずなのに trace に痕跡なし」状態だったため。
        #
        # 注: runtime.trace_recorder は session 作成後に set_trace_recorder() で
        # 後から差し込まれるケース (実験スクリプト経路) があるため、
        # callable provider 経由で use 時に look-up する。
        self.tool_call_loop_guard = ToolCallLoopGuardService(
            observation_buffer=self.observation_buffer,
            time_label_provider=self._time_label,
            trace_recorder_provider=lambda: getattr(
                self.runtime, "trace_recorder", None
            ),
            current_tick_provider=(
                self.runtime.current_tick
                if hasattr(self.runtime, "current_tick")
                else None
            ),
        )
        # 同じ instance を prompt_builder にも共有させる。record_and_check で
        # 進めた streak を peek_streak で読んで、instruction 末尾に「同じ手
        # 連続中」warning prefix を載せる。 recent_events に並ぶ既存の警告は
        # 埋もれやすいので、recency bias が効く instruction 直前にも同じ意図
        # の prompt を流して二重に attention を取りに行く。
        if hasattr(self.runtime, "set_tool_call_loop_guard"):
            self.runtime.set_tool_call_loop_guard(self.tool_call_loop_guard)
        # PR 5 (#227): memo 完了 hint。LLM が memo_done を呼ばずに memo を
        # 放置するケースを救済するため、action_summary / result_summary と
        # 未完了 memo の content を SequenceMatcher で比較し、類似度が高ければ
        # 「memo を完了したかも」hint を result.message に append する。
        # PR #230 で本家経路に配線済みだが、world_runtime の独自 turn 実行は
        # 経由しないため、ここで wiring に直接組み込む。
        runtime_config = getattr(self.runtime, "_runtime_config", None)
        memo_tools_enabled = bool(
            getattr(runtime_config, "memo_tools_enabled", True)
        )
        memo_store = getattr(self.runtime, "_todo_store", None)
        # runtime 側で aux being stack を初期化しておく。phase_b の
        # _acting_being_for が動くために必要。idempotent な呼び出し。
        if memo_tools_enabled and memo_store is not None and hasattr(
            self.runtime, "_wire_auxiliary_tool_stack"
        ):
            try:
                self.runtime._wire_auxiliary_tool_stack()
            except Exception:
                logger.warning(
                    "_wire_auxiliary_tool_stack failed; "
                    "MemoCompletionHintService will be disabled",
                    exc_info=True,
                )
        if memo_tools_enabled and memo_store is not None:
            self.memo_completion_hint_service: Optional[MemoCompletionHintService] = (
                MemoCompletionHintService(memo_store=memo_store)
            )
        else:
            self.memo_completion_hint_service = None
        # Issue #264 後続 B1: speech_say の audience resolver。
        # runtime の spot_graph_repo / player_status_repo / SoundPropagationService を
        # 集めて事前 audience 問い合わせを可能にする。これにより speech 結果
        # message に「届いた人数」を含められ、agent が空振りを学習できる。
        spot_graph_repo = getattr(self.runtime, "_spot_graph_repo", None)
        player_status_repo = getattr(self.runtime, "_player_status_repo", None)
        self.speech_audience_resolver: Optional[SpeechAudienceResolver] = None
        if spot_graph_repo is not None and player_status_repo is not None:
            self.speech_audience_resolver = SpeechAudienceResolver(
                spot_graph_repository=spot_graph_repo,
                player_status_repository=player_status_repo,
                sound_propagation_service=SoundPropagationService(),
                player_perception_policy=getattr(
                    self.runtime, "_player_perception_policy", None
                ),
                departed_position_store=getattr(
                    self.runtime, "_departed_position_store", None
                ),
            )
        # PR 7 (#227): ツール名→ハンドラの dispatch table。本家
        # ToolCommandMapper.execute と構造を揃え、巨大 if-elif を排除する。
        # 各ハンドラは (player_id, arguments, runtime_context) を受けて
        # LlmCommandResultDto を返す。
        self._tool_handlers: Dict[
            str,
            Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto],
        ] = {
            # PR-θ1/θ2/θ3/θ4/θ5/θ6 (経路統合): TRAVEL_TO / EXPLORE / INTERACT /
            # LISTEN / WAIT / SET_SUB_LOCATION の登録は削除した。
            # - travel_to / explore / interact / listen / wait は
            #   _wire_missing_spot_graph_tools が SpotGraphToolExecutor 側
            #   handler を上書き wire する
            # - set_sub_location は脱出ランタイムでは意図的に未対応
            #   (ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS で LLM 露出も除外)
            #   なので wire しない。SpotGraphToolExecutor._set_sub_location
            #   は将来の別ランタイム用に残す。仮に何らかの経路で呼ばれても、
            #   default `_execute_tool` の UNSUPPORTED_TOOL 経路で正しく弾く。
            TOOL_NAME_SPEECH: self._handle_speech,
            TOOL_NAME_TODO_ADD: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_ADD),
            TOOL_NAME_TODO_LIST: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_LIST),
            TOOL_NAME_TODO_COMPLETE: self._make_auxiliary_tool_handler(
                TOOL_NAME_TODO_COMPLETE
            ),
            # Issue #526 後続: memory_recall_episodes も aux 経路で dispatch する。
            # ``runtime.run_llm_auxiliary_tool`` が ``_memory_recall_tool_executor``
            # を併用するよう PR #535 で配線済み。tool 定義は episodic_stack ON
            # のときだけ ``get_tool_definitions`` で expose される。
            TOOL_NAME_MEMORY_RECALL_EPISODES: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_RECALL_EPISODES
            ),
            TOOL_NAME_MEMORY_EXPLORE_RELATED: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_EXPLORE_RELATED
            ),
            TOOL_NAME_MEMORY_SEARCH_SEMANTIC: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_SEARCH_SEMANTIC
            ),
            # PR-D (#588) 後続 fix: memory_recall_by_handle も同じ aux 経路に
            # 載せる。SSOT である本テーブルにエントリが無いと
            # ``execute_tool`` の dispatcher が UNSUPPORTED_TOOL を返す silent
            # failure になる (= Run D で 30 tick 中 2 回呼ばれたが両方失敗した
            # 直接原因)。tool 定義は afterglow_store + slot_store が揃った
            # ときだけ ``get_tool_definitions`` で expose されるので、ここに
            # 居ても afterglow off の run では一切呼ばれない (= 安全)。
            TOOL_NAME_MEMORY_RECALL_BY_HANDLE: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_RECALL_BY_HANDLE
            ),
        }
        # #344 配線漏れ修正: spot_graph_use_item / attack / give_item /
        # pickup_item / drop_item / prepare_action は application 層 (executor)
        # に実装があるが、experiment runtime の _tool_handlers に dispatch が
        # 無く UNSUPPORTED_TOOL に化けていた。executor を遅延構築し、これら
        # の handler を _tool_handlers に追加する。
        self._spot_graph_executor: Optional[Any] = None
        wire_missing_spot_graph_tools(self)
    def attach_action_failed_wiring(
        self,
        emitter: ActionFailedObservationEmitter,
        generator: IntentIdGenerator,
    ) -> None:
        """二段構築の 2 段目: ActionFailed 観測の依存を後付け注入する。"""
        self.action_failed_emitter = emitter
        self.intent_id_generator = generator

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        phase_a = self.run_phase_a(player_id)
        return self.run_phase_b(phase_a)

    def run_phase_a(self, player_id: PlayerId) -> LlmPhaseAResult:
        return run_phase_a(self, player_id)

    def run_phase_b(self, phase_a: LlmPhaseAResult) -> LlmCommandResultDto:
        return run_phase_b(self, phase_a)

    def _build_tools_payload(
        self, player_id: PlayerId, *, tool_schema_mode: str = "legacy"
    ) -> list[dict[str, Any]]:
        return build_tools_payload(self, player_id, tool_schema_mode=tool_schema_mode)

    def _maybe_interrupt_busy(
        self, player_id: PlayerId, tool_name: str
    ):
        return maybe_interrupt_busy(self, player_id, tool_name)

    def _restore_nav_state(self, player_id: PlayerId, nav_snapshot) -> None:
        restore_nav_state(self, player_id, nav_snapshot)

    def _reason_tool_is_not_offered(
        self,
        name: str,
        player_id: PlayerId,
        *,
        offered_tool_names_at_prompt,
    ):
        return reason_tool_is_not_offered(
            self,
            name,
            player_id,
            offered_tool_names_at_prompt=offered_tool_names_at_prompt,
        )

    def _llm_session_id(self, player_id: PlayerId) -> str:
        return llm_session_id(self, player_id)

    def _llm_session_kwargs(self, player_id: PlayerId) -> dict[str, str]:
        return llm_session_kwargs(self, player_id)

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        return coerce_arguments(raw_arguments)

    def _time_label(self) -> str:
        runtime_label = getattr(self.runtime, "_time_label", None)
        if callable(runtime_label):
            return runtime_label()
        tick = self.runtime.current_tick()
        hours = tick % 24
        return f"深夜 {hours}:00" if hours < 6 else f"{hours}:00"

    def _definitions_across_phases(self) -> list:
        return definitions_across_phases(self)

    def _wire_missing_spot_graph_tools(self) -> None:
        wire_missing_spot_graph_tools(self)

    def _validate_tool_handler_consistency(self) -> None:
        validate_tool_handler_consistency_for_wiring(self)

    def _execute_tool(
        self,
        player_id: PlayerId,
        name: str,
        arguments: dict[str, Any],
        runtime_context: Any,
        *,
        offered_tool_names_at_prompt,
    ) -> LlmCommandResultDto:
        return execute_tool(
            self, player_id, name, arguments, runtime_context,
            offered_tool_names_at_prompt=offered_tool_names_at_prompt,
        )

    @staticmethod
    def _action_failure_key(entry: Any) -> Optional[tuple[str, str, str]]:
        return action_failure_key(entry)

    @staticmethod
    def _parse_assessment_tool_call(
        tool_call: Optional[dict],
    ) -> tuple[Optional[dict[str, str]], str]:
        return parse_assessment_tool_call(tool_call)

    def _handle_speech(self, player_id, arguments, runtime_context):
        return handle_speech(self, player_id, arguments, runtime_context)

    def _resolve_whisper_target(self, target_label, targets):
        return resolve_whisper_target(self, target_label, targets)

    def _make_auxiliary_tool_handler(self, tool_name):
        return make_auxiliary_tool_handler(self, tool_name)

    @staticmethod
    def _adapt_executor_handler_with_resolver(
        raw_handler,
        tool_name: str,
        argument_resolver,
        *,
        invalid_label_failure_builder=None,
    ):
        return adapt_executor_handler_with_resolver(
            raw_handler, tool_name, argument_resolver,
            invalid_label_failure_builder=invalid_label_failure_builder,
        )

    @staticmethod
    def _build_interact_invalid_label_failure(runtime_context, arguments, exc):
        return build_interact_invalid_label_failure(runtime_context, arguments, exc)

    @staticmethod
    def _build_travel_to_invalid_label_failure(runtime_context, arguments, exc):
        return build_travel_to_invalid_label_failure(runtime_context, arguments, exc)

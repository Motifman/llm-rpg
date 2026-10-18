"""Session-local LLM loop wiring for the world runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
        SpotGraphArgumentResolver,
    )

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import IntentIdGenerator
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.loop_diagnosis import LoopDiagnosis
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    DEFAULT_MIN_PROBABILITY,
    MemoCompletionHintService,
    PendingTodo,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (
    SemanticRepeatDetector,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
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
from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (
    ToolNameRescue,
)
from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    WorldLlmTurnTrigger,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
    TOOL_NAME_SPEECH,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceResolver,
)
from ai_rpg_world.being.domain.memo_book import MemoKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)

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
    prompt_dataset_sink: Any | None = None
    max_self_reschedule_streak: int = 5
    action_failed_emitter: ActionFailedObservationEmitter | None = None
    #: tool_dispatch が組んだ resolver。注入漏れを外から確かめるために残す。
    argument_resolver: SpotGraphArgumentResolver | None = None
    intent_id_generator: IntentIdGenerator | None = None
    #: 型付きの判断を引く口 (#1319)。profile が求めなければ None。
    #:
    #: None のときは判断を引かず、既存のルールで決める。**None を「判断が
    #: 偽だった」と同じに扱わない。** 引いていないことと引いた結果は別の事実
    #: で、trace で区別できなければ OFF の run と全件 fallback の run が同じに
    #: 見える。
    typed_judgment_port: ITypedJudgmentPort | None = None
    #: 存在しない tool 名から意図した tool を意味で選ぶ口 (#1413)。
    #: typed_judgment_port から __post_init__ で組む。None なら文字の類似度だけで提案する。
    tool_name_rescue: ToolNameRescue | None = field(default=None, init=False)

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
            loop_diagnosis=self._build_loop_diagnosis(),
            semantic_repeat_detector=self._build_semantic_repeat_detector(),
            location_provider=(
                self.runtime.get_player_spot_name
                if hasattr(self.runtime, "get_player_spot_name")
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
        runtime_config = getattr(self.runtime, "_runtime_config", None)
        min_probability = float(
            getattr(
                runtime_config,
                "typed_judgment_memo_min_probability",
                DEFAULT_MIN_PROBABILITY,
            )
        )
        self.memo_completion_hint_service: MemoCompletionHintService | None = None
        if runtime_config is not None:
            # #1628: メモ帳のやることが済んだかを問う。自動では消さない。
            self.memo_completion_hint_service = MemoCompletionHintService(
                pending_todos=self._pending_todos,
                judgment_port=self.typed_judgment_port,
                min_probability=min_probability,
            )
        if self.typed_judgment_port is not None:
            self.tool_name_rescue = ToolNameRescue(port=self.typed_judgment_port)
        # Issue #264 後続 B1: speech_say の audience resolver。
        # runtime の spot_graph_repo / player_status_repo / SoundPropagationService を
        # 集めて事前 audience 問い合わせを可能にする。これにより speech 結果
        # message に「届いた人数」を含められ、agent が空振りを学習できる。
        spot_graph_repo = getattr(self.runtime, "_spot_graph_repo", None)
        player_status_repo = getattr(self.runtime, "_player_status_repo", None)
        self.speech_audience_resolver: SpeechAudienceResolver | None = None
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
        self._tool_handlers: dict[
            str,
            Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto],
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
            # #1623: 定義は目次を出す設定でだけ get_tool_definitions が出す。
            TOOL_NAME_EPISODE_RECALL: self._make_auxiliary_tool_handler(
                TOOL_NAME_EPISODE_RECALL
            ),
            TOOL_NAME_EPISODE_REVISE_INDEX: self._make_auxiliary_tool_handler(
                TOOL_NAME_EPISODE_REVISE_INDEX
            ),
        }
        # #344 配線漏れ修正: spot_graph_use_item / attack / give_item /
        # pickup_item / drop_item / prepare_action は application 層 (executor)
        # に実装があるが、experiment runtime の _tool_handlers に dispatch が
        # 無く UNSUPPORTED_TOOL に化けていた。executor を遅延構築し、これら
        # の handler を _tool_handlers に追加する。
        public_sns_executor = getattr(self.runtime, "_public_sns_executor", None)
        if public_sns_executor is not None:
            self._tool_handlers["sns_read"] = lambda pid, args, ctx: public_sns_executor.read(int(pid), args, ctx)
            self._tool_handlers["sns_publish"] = lambda pid, args, ctx: public_sns_executor.publish(int(pid), args, ctx)
        self._spot_graph_executor: Any | None = None
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
    ) -> tuple[bool, PlayerSpotNavigationState | None]:
        return maybe_interrupt_busy(self, player_id, tool_name)

    def _restore_nav_state(
        self, player_id: PlayerId, nav_snapshot: PlayerSpotNavigationState
    ) -> None:
        restore_nav_state(self, player_id, nav_snapshot)

    def _reason_tool_is_not_offered(
        self,
        name: str,
        player_id: PlayerId,
        *,
        offered_tools_at_prompt: Mapping[str, str | None],
    ) -> LlmCommandResultDto | None:
        return reason_tool_is_not_offered(
            self,
            name,
            player_id,
            offered_tools_at_prompt=offered_tools_at_prompt,
        )

    def _llm_session_id(self, player_id: PlayerId) -> str:
        return llm_session_id(self, player_id)

    def _llm_session_kwargs(self, player_id: PlayerId) -> dict[str, str]:
        return llm_session_kwargs(self, player_id)

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        return coerce_arguments(raw_arguments)

    def _build_loop_diagnosis(self) -> LoopDiagnosis | None:
        """profile が繰り返しの理由の判定を求め、判断ポートがあるときだけ組む (#1411)。"""
        config = getattr(self.runtime, "_runtime_config", None)
        if (
            self.typed_judgment_port is None
            or config is None
            or not config.typed_judgment_loop_diagnosis_enabled
        ):
            return None
        return LoopDiagnosis(port=self.typed_judgment_port)

    def _build_semantic_repeat_detector(self) -> SemanticRepeatDetector | None:
        """profile が意味上の繰り返しの検出を求め、判断ポートがあるときだけ組む (#1412)。"""
        config = getattr(self.runtime, "_runtime_config", None)
        if (
            self.typed_judgment_port is None
            or config is None
            or not config.typed_judgment_semantic_repeat_enabled
        ):
            return None
        return SemanticRepeatDetector(
            self.typed_judgment_port,
            player_name_resolver=self.runtime.get_player_name,
            window_size=int(config.typed_judgment_semantic_repeat_window),
            threshold=float(config.typed_judgment_semantic_repeat_min_probability),
            trace_recorder_provider=lambda: getattr(self.runtime, "trace_recorder", None),
        )

    def _pending_todos(self, being_id: BeingId) -> list[PendingTodo]:
        book = self.runtime._being_memo_store.get(being_id)
        return [
            PendingTodo(id=m.memo_id, content=m.text, handle=m.handle)
            for m in book.memos
            if m.kind is MemoKind.TODO
        ]

    def _time_label(self) -> str:
        runtime_label = getattr(self.runtime, "_time_label", None)
        if callable(runtime_label):
            label: str = runtime_label()
            return label
        tick = self.runtime.current_tick()
        hours = tick % 24
        return f"深夜 {hours}:00" if hours < 6 else f"{hours}:00"

    def _definitions_across_phases(self) -> list[Any]:
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
        offered_tools_at_prompt: Mapping[str, str | None],
    ) -> LlmCommandResultDto:
        return execute_tool(
            self, player_id, name, arguments, runtime_context,
            offered_tools_at_prompt=offered_tools_at_prompt,
        )

    @staticmethod
    def _action_failure_key(entry: Any) -> tuple[str, str, str] | None:
        return action_failure_key(entry)

    @staticmethod
    def _parse_assessment_tool_call(
        tool_call: dict[str, Any] | None,
    ) -> tuple[dict[str, str] | None, str]:
        return parse_assessment_tool_call(tool_call)

    def _handle_speech(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        return handle_speech(self, player_id, arguments, runtime_context)

    def _resolve_whisper_target(
        self, target_label: str, targets: dict[str, Any]
    ) -> Any | None:
        return resolve_whisper_target(self, target_label, targets)

    def _make_auxiliary_tool_handler(
        self, tool_name: str
    ) -> Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto]:
        return make_auxiliary_tool_handler(self, tool_name)

    @staticmethod
    def _adapt_executor_handler_with_resolver(
        raw_handler: Callable[..., LlmCommandResultDto],
        tool_name: str,
        argument_resolver: Any,
        *,
        invalid_label_failure_builder: Any = None,
    ) -> Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto]:
        return adapt_executor_handler_with_resolver(
            raw_handler, tool_name, argument_resolver,
            invalid_label_failure_builder=invalid_label_failure_builder,
        )

    @staticmethod
    def _build_interact_invalid_label_failure(
        runtime_context: Any, arguments: dict[str, Any], exc: Exception
    ) -> LlmCommandResultDto:
        return build_interact_invalid_label_failure(runtime_context, arguments, exc)

    @staticmethod
    def _build_travel_to_invalid_label_failure(
        runtime_context: Any, arguments: dict[str, Any], exc: Exception
    ) -> LlmCommandResultDto:
        return build_travel_to_invalid_label_failure(runtime_context, arguments, exc)

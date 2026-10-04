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

from ai_rpg_world.application.being.expectation.forming import (
    ExpectationFormingService,
)
from ai_rpg_world.application.being.expectation.grounds import (
    MemoryStoreInMindTextReader,
)
from ai_rpg_world.application.being.expectation.settlement import (
    ExpectationSettlementService,
)
from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import IntentIdGenerator
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
)
from ai_rpg_world.application.llm.services.goal_completion_hint_service import (
    GoalCompletionHintService,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.loop_diagnosis import LoopDiagnosis
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    DEFAULT_MIN_PROBABILITY,
    MemoCompletionHintService,
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
    #: tick の終わりに「いま動く必要があるか」を問う起動判定。profile が求めなければ None。
    #: runtime_manager が typed_judgment_port から組んで差し込む。
    turn_gate: Any | None = None
    #: 存在しない tool 名から意図した tool を意味で選ぶ口 (#1413)。
    #: typed_judgment_port から __post_init__ で組む。None なら文字の類似度だけで提案する。
    tool_name_rescue: ToolNameRescue | None = field(default=None, init=False)
    #: ターンの終わりに予期を清算する口 (#1440)。profile が求めなければ None。
    expectation_settlement: ExpectationSettlementService | None = field(
        default=None, init=False
    )
    #: 行動に書かれた予期を積む口 (#1441)。profile が求めなければ None。
    expectation_forming: ExpectationFormingService | None = field(
        default=None, init=False
    )

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
            # #1322: profile が型付き判断を求めていれば、文字の重なりでなく
            # 意味で完了を判定する。求めていなければ従来の重なり判定で動く。
            self.memo_completion_hint_service: MemoCompletionHintService | None = (
                MemoCompletionHintService(
                    memo_store=memo_store,
                    judgment_port=self.typed_judgment_port,
                    min_probability=float(
                        getattr(
                            runtime_config,
                            "typed_judgment_memo_min_probability",
                            DEFAULT_MIN_PROBABILITY,
                        )
                    ),
                )
            )
        else:
            self.memo_completion_hint_service = None
        self.goal_completion_hint_service = self._build_goal_completion_hint_service()
        self.expectation_settlement = self._build_expectation_settlement()
        self.expectation_forming = self._build_expectation_forming()
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

    def _build_goal_completion_hint_service(self) -> GoalCompletionHintService | None:
        """profile が目的の hint を求めたときだけ組む (#1448)。

        前提が欠けたまま有効にした profile は起動前に落とす。黙って無効にすると、
        run 後に「hint が 0 件」が閾値のせいか配線のせいか見分けられない。
        goal_outcome が tool に出ていない run で組むと、存在しない申告を勧める。
        """
        config = getattr(self.runtime, "_runtime_config", None)
        if config is None or not config.typed_judgment_goal_hint_enabled:
            return None
        port = self.typed_judgment_port
        goal_store = getattr(self.runtime, "_goal_journal_store", None)
        goal_outcome_offered = bool(
            getattr(self.runtime, "_goal_revision_enabled", False)
        )
        if port is None or goal_store is None or not goal_outcome_offered:
            missing = [
                requirement
                for requirement, present in (
                    ("TYPED_JUDGMENT_PROVIDER", port is not None),
                    ("GOAL_STORE_ENABLED", goal_store is not None),
                    ("GOAL_REVISION_ENABLED", goal_outcome_offered),
                )
                if not present
            ]
            raise ValueError(
                "TYPED_JUDGMENT_GOAL_HINT_ENABLED requires " + ", ".join(missing)
            )
        return GoalCompletionHintService(
            goal_store,
            judgment_port=port,
            min_probability=float(config.typed_judgment_goal_hint_min_probability),
        )

    def _build_expectation_settlement(self) -> ExpectationSettlementService | None:
        """profile が予期の清算を求めたときだけ組む (#1440)。

        判断ポートが無いまま有効にした profile は起動前に落とす。黙って無効にすると、
        清算の trace が 0 件の run を「予期が無かった」と読み違える。
        """
        config = getattr(self.runtime, "_runtime_config", None)
        if config is None or not config.expectation_settlement_enabled:
            return None
        if self.typed_judgment_port is None:
            raise ValueError(
                "EXPECTATION_SETTLEMENT_ENABLED requires TYPED_JUDGMENT_PROVIDER"
            )
        return ExpectationSettlementService(
            self.runtime._expectation_store,
            judgment_port=self.typed_judgment_port,
            dispatcher=self.runtime._expectation_dispatcher,
            max_open=int(config.expectation_settlement_max_open),
            timeline_turns=int(config.expectation_settlement_timeline_turns),
            grounds_reader=self._in_mind_text_reader(),
            max_grounds_questions=int(config.expectation_grounds_max_questions),
            grounds_min_probability=float(config.expectation_grounds_min_probability),
            trace_recorder_provider=lambda: getattr(self.runtime, "trace_recorder", None),
        )

    def _in_mind_text_reader(self) -> MemoryStoreInMindTextReader:
        """プロンプトの想起と同じ store から、頭にあった信念とエピソードの本文を引く (#1484)。

        episodic stack が無い run では本文を引けず、根拠の問いは出ない。外した
        理由は清算の trace の ``grounds`` に残る。
        """
        stack = getattr(self.runtime, "_episodic_stack", None)
        return MemoryStoreInMindTextReader(
            semantic_store=getattr(stack, "semantic_memory_store", None),
            episode_store=getattr(stack, "episode_store", None),
            journal_store=getattr(stack, "reinterpretation_journal", None),
        )

    def _build_expectation_forming(self) -> ExpectationFormingService | None:
        """profile が予期の引数を求めたときだけ組む (#1441)。"""
        config = getattr(self.runtime, "_runtime_config", None)
        if config is None or not config.expectation_argument_enabled:
            return None
        return ExpectationFormingService(
            self.runtime._expectation_store,
            undated_term_turns=int(config.expectation_undated_term_turns),
            dated_term_turns=int(config.expectation_dated_term_turns),
        )

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

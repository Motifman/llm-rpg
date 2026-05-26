"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``EscapeGameRuntime`` / scenario loaders / session lifecycle to
the API layer.  Methods that are not yet backed by real logic return
stub data so that the full API surface remains exercisable.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_env,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMappingError
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterDetailResponse,
    CharacterInSpotResponse,
    CharacterSummaryResponse,
    CharacterUpdateRequest,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatSendRequest,
    EventLogResponse,
    InventoryItemResponse,
    InventoryResponse,
    ResultImpressionResponse,
    ResultRelationshipResponse,
    ResultTimelineResponse,
    SaveListResponse,
    SaveSlotResponse,
    SessionCreateRequest,
    SessionStateResponse,
    SessionSummaryResponse,
    SpotConnectionResponse,
    SpotObjectResponse,
    SpotViewResponse,
    WorldDetailResponse,
    WorldSummaryResponse,
)

logger = logging.getLogger(__name__)


def _character_to_escape_prompt_input(
    character: Optional[CharacterDetailResponse],
) -> Optional[EscapeCharacterPromptInput]:
    if character is None:
        return None
    return EscapeCharacterPromptInput(
        character_id=character.id,
        name=character.name,
        first_person=character.first_person or "私",
        personality_tags=tuple(character.personality_tags or ()),
        appearance=character.appearance or "",
        speech_samples=tuple(character.speech_samples or ()),
        fragmented_memory=character.fragmented_memory or "",
        values=character.values or "",
        strengths=character.strengths or "",
        weaknesses=character.weaknesses or "",
        interpersonal_tendency=character.interpersonal_tendency or "",
        behavioral_rules=tuple(character.behavioral_rules or ()),
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _EscapeSpawnAllPlayersLlmResolver(ILLMPlayerResolver):
    """スポーンした全員をプレゼン層脱出セッションでは LLM ターン対象とみなす。"""

    spawn_player_ids: frozenset[int]

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return player_id.value in self.spawn_player_ids


# ──────────────────────────────────────────────────────────────────
# 失敗 message learnable 化ヘルパーは ``application/llm/services/
# failure_helpers.py`` に集約済 (Issue #168 で executor 横断展開のため
# 共通モジュールへ昇格)。本ファイル内では既存呼び出し / テストの後方
# 互換のため private alias を再エクスポートする。
#
# 旧: ``runtime_manager._list_object_labels(targets)``
# 新: ``failure_helpers.list_object_labels(targets)`` と同じ実装が動く。
# ──────────────────────────────────────────────────────────────────

from ai_rpg_world.application.llm.services.failure_helpers import (  # noqa: E402
    list_destination_labels as _list_destination_labels,
    list_object_labels as _list_object_labels,
    list_player_labels as _list_player_labels,
    list_targets_of_kind as _list_targets_of_kind,
)


def _safe_get_str(mapper: Any, namespace: str, numeric_id: int) -> str:
    """Return the string ID for *numeric_id*, falling back to str(numeric_id)."""
    try:
        return mapper.get_str(namespace, numeric_id)
    except (ScenarioIdMappingError, KeyError):
        return str(numeric_id)


def _read_scenario_metadata(path: Path) -> Optional[Dict[str, Any]]:
    """Read only the metadata section from a scenario JSON without full parse."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read scenario %s: %s", path, exc)
        return None


@dataclass
class _QueuedTurnTrigger:
    """Minimal turn scheduler used until the API runtime is wired to real LLM turns."""

    pending_player_ids: set[int] = field(default_factory=set)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)

    def run_scheduled_turns(self) -> None:
        self.pending_player_ids.clear()


@dataclass
class _EscapeGameLlmTurnTrigger:
    """Queues escape-game LLM turns and runs them against the session runtime."""

    wiring: "_EscapeGameLlmWiring"
    max_turns: int = 5
    pending_player_ids: set[int] = field(default_factory=set)
    _turn_counts: dict[int, int] = field(default_factory=dict)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)
        self._turn_counts[player_id.value] = 0

    def run_scheduled_turns(self) -> None:
        to_run = list(self.pending_player_ids)
        self.pending_player_ids.clear()
        for player_id_value in to_run:
            result = self.wiring.run_turn(PlayerId(player_id_value))
            current_count = self._turn_counts.get(player_id_value, 0) + 1
            if result.was_no_op:
                self._turn_counts.pop(player_id_value, None)
            elif result.should_reschedule or current_count < self.max_turns:
                self.pending_player_ids.add(player_id_value)
                self._turn_counts[player_id_value] = current_count
            else:
                self._turn_counts.pop(player_id_value, None)


@dataclass
class _EscapeGameLlmWiring:
    """Session-local LLM loop for the escape-game runtime.

    **Two-phase construction invariant**:
    ``action_failed_emitter`` と ``intent_id_generator`` は ``ObservationTurnScheduler``
    → ``ActionFailedObservationEmitter`` の構築連鎖が ``llm_turn_trigger`` を
    必要とするため、本クラスの ``__init__`` 直後に注入する必要がある。
    ``create_session`` の流れは:

        1. ``_EscapeGameLlmWiring(...)`` を ctor で作成 (内部で trigger 生成)
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
    llm_client: Any = field(default_factory=create_llm_client_from_env)
    max_turns: int = 5
    # 失敗 DTO を ActionFailed 観測に変換する emitter (Optional)。
    # ``attach_action_failed_wiring`` で配線される。None の場合は失敗観測を
    # 発行しない (後方互換 / テスト用ショートカット)。
    action_failed_emitter: Optional[ActionFailedObservationEmitter] = None
    # ActionFailed 観測の intent.intent_id を払い出すカウンタ。
    # action_failed_emitter とセットで使う想定。
    intent_id_generator: Optional[IntentIdGenerator] = None

    def __post_init__(self) -> None:
        self.observation_appender = ObservationAppender(self.observation_buffer)
        self.llm_turn_trigger = _EscapeGameLlmTurnTrigger(
            wiring=self,
            max_turns=self.max_turns,
        )
        # PR 4 (#227): 同一ツール連打を engine 側で検知し、警告を観測として
        # 注入する loop guard。PR #230 で LlmAgentOrchestrator 経由で配線
        # していたが、escape_game の独自 turn 実行はそれを経由しないため、
        # ここで wiring に直接組み込む。閾値は ToolCallLoopGuardService の
        # 既定値 (wait=3 / travel_to=2 / interact=4 / その他=5) を使う。
        self.tool_call_loop_guard = ToolCallLoopGuardService(
            observation_buffer=self.observation_buffer,
        )

    def attach_action_failed_wiring(
        self,
        emitter: ActionFailedObservationEmitter,
        generator: IntentIdGenerator,
    ) -> None:
        """二段構築の 2 段目: ActionFailed 観測の依存を後付け注入する。

        ``create_session`` でのみ呼ぶ想定。両方セットで呼ぶことで、
        emitter だけ刺さって generator が None という中間状態を避ける。
        """
        self.action_failed_emitter = emitter
        self.intent_id_generator = generator

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        prompt = self.runtime.build_full_prompt(player_id)
        messages = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self.runtime.get_tool_definitions()
        ]
        tool_call = self.llm_client.invoke(messages, tools, "required")
        if tool_call is None:
            result = LlmCommandResultDto(
                success=False,
                message="LLM がツールを返しませんでした。",
                error_code="NO_TOOL_CALL",
                remediation="必ずいずれか 1 つのツールを呼び出してください。",
                should_reschedule=False,
                was_no_op=True,
            )
            self.runtime._record_action_result(
                player_id,
                "LLM API 呼び出し",
                result.message,
            )
            return result

        name = str(tool_call.get("name", ""))
        arguments = self._coerce_arguments(tool_call.get("arguments"))
        # Phase 1d: ACTION 自動 trace (実行前)。runtime に trace_recorder が
        # 注入されていれば記録。LlmAgentOrchestrator 経路を通らない escape_game
        # 専用 wiring のための補完。
        trace_recorder = getattr(self.runtime, "trace_recorder", None)
        current_tick: Optional[int] = None
        if trace_recorder is not None:
            try:
                current_tick = int(self.runtime.current_tick())
            except Exception:
                current_tick = None
            try:
                trace_recorder.record(
                    "action",
                    tick=current_tick,
                    player_id=int(player_id.value),
                    tool=name,
                    arguments=arguments,
                )
            except Exception:
                logger.exception("trace_recorder.record(action) failed")
        try:
            result = self._execute_tool(
                player_id,
                name,
                arguments,
                prompt["tool_runtime_context"],
            )
        except Exception as exc:
            result = LlmCommandResultDto(
                success=False,
                message=f"LLM ツール実行に失敗しました: {exc}",
                error_code="LLM_TOOL_EXECUTION_FAILED",
                remediation="現在の状況に表示されたラベルと利用可能な action_name を確認してください。",
            )
        skip_duplicate_action_log = result.success and name in (
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        )
        if not skip_duplicate_action_log:
            self.runtime._record_action_result(
                player_id,
                f"{name}({json.dumps(arguments, ensure_ascii=False)})",
                result.message,
            )
        if trace_recorder is not None:
            try:
                trace_recorder.record(
                    "action_result",
                    tick=current_tick,
                    player_id=int(player_id.value),
                    tool=name,
                    success=result.success,
                    error_code=result.error_code,
                    result_summary=result.message,
                )
            except Exception:
                logger.exception("trace_recorder.record(action_result) failed")
        # PR 4 (#227): 同一ツール連打を検知し警告観測を注入する。
        # action_result の記録後に呼ぶことで、失敗を繰り返すケースも検知対象
        # に入る。閾値超過時は次ターンの prompt 構築時に observation buffer
        # から drain されて LLM に警告が届く。
        if name:
            try:
                self.tool_call_loop_guard.record_and_check(
                    player_id,
                    name,
                    arguments,
                )
            except Exception:
                logger.exception("tool_call_loop_guard.record_and_check failed")
        # 失敗 DTO のとき ActionFailed 観測を該当プレイヤーへ投入する。
        # post-hoc に Intent VO を構築し observer に渡す (intent queue 経由は
        # しない — 即時 path で意味のある最小 wire-in)。LLM API レベルや
        # 配線エラーは emitter 側で除外される。
        if not result.success:
            self._emit_action_failed_observation(player_id, name, arguments, result)
        return result

    def _emit_action_failed_observation(
        self,
        player_id: PlayerId,
        tool_name: str,
        arguments: dict[str, Any],
        result: LlmCommandResultDto,
    ) -> None:
        if self.action_failed_emitter is None or self.intent_id_generator is None:
            return
        # 空 tool_name は LLM 出力の欠陥 (例: ``{"name": ""}``)。Intent VO は
        # 非空 str を要求するため "unknown" 等で穴埋めすると観測の tool_name
        # フィールドが false-positive な値で汚れる。診断用に warning を残し、
        # 観測そのものは emit しない (LLM API レベル失敗の扱いに準じる)。
        if not tool_name:
            logger.warning(
                "Skipping ActionFailed emission: empty tool_name from LLM "
                "(player=%s error_code=%s)",
                player_id.value,
                result.error_code,
            )
            return
        try:
            current_tick_value = int(self.runtime.current_tick())
            tick = WorldTick(current_tick_value)
            intent = Intent(
                intent_id=self.intent_id_generator.next_id(),
                player_id=player_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                phase=phase_for_tool(tool_name),
                submitted_at_tick=tick,
                complete_at_tick=tick,
            )
            self.action_failed_emitter.on_resolution_failure(intent, result)
        except Exception:
            # observer 発火が turn 結果を倒さないよう吸収 (best-effort)。
            logger.exception(
                "Failed to emit ActionFailed observation for player=%s tool=%s",
                player_id.value,
                tool_name,
            )

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str) and raw_arguments:
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _execute_tool(
        self,
        player_id: PlayerId,
        name: str,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_SAY,
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_WAIT,
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_COMPLETE,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_WHISPER,
        )

        targets = getattr(runtime_context, "targets", {})
        if name == TOOL_NAME_SPOT_GRAPH_EXPLORE:
            result = self.runtime.do_explore(player_id)
            if result.discovery_descriptions:
                message = "発見: " + " / ".join(result.discovery_descriptions)
            else:
                # F2: 「新しい発見はなかった」だけだと LLM が「部屋に何もない」
                # と誤解し interact しなくなる癖がある。spot view に既に表示
                # されている可視オブジェクトを併記して、LLM の "見えない"
                # 誤認を防ぐ。
                visible_objects = _list_object_labels(targets)
                if visible_objects:
                    message = (
                        "新しい発見はなかった。"
                        f"既に見えているオブジェクト: {visible_objects}"
                        " (interact するにはこのラベルを object_label に指定する)"
                    )
                else:
                    message = "新しい発見はなかった (この場所に interactable なオブジェクトは無い)"
            return with_inner_thought_empty_warning(
                name, arguments, LlmCommandResultDto(success=True, message=message)
            )

        if name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO:
            label = str(arguments.get("destination_label", ""))
            target = targets.get(label)
            # PR 3 (#227): label miss なら display_name (スポット名) でフォール
            # バック解決を試みる。LLM が "S1" の代わりに「閲覧室」のような不変
            # なスポット名を直接渡しても動くようにする。本家経路の
            # _argument_resolvers/spot_graph_resolver.py が同じロジックを
            # 既に持つが、escape_game の _execute_tool はそちらを経由しない
            # ため、ここで同等のフォールバックを行う。PR 7 で _execute_tool
            # を本家 resolver 経由に統合した際に削除予定。
            if target is None or target.spot_id is None:
                for candidate in targets.values():
                    if (
                        candidate.kind == "spot_graph_destination"
                        and candidate.display_name == label
                        and candidate.spot_id is not None
                    ):
                        target = candidate
                        break
            if target is None or target.spot_id is None:
                # F1: 失敗時に有効ラベルを列挙して LLM が次の試行で正しい値を
                # 選べるようにする (前回は message に valid 一覧が無く同じ
                # 失敗を繰り返していた)。
                valid_destinations = _list_destination_labels(targets)
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        f"移動先が見つかりません: {label}。"
                        f"有効な destination_label: {valid_destinations or '(この場所からの移動先なし)'}"
                    ),
                    error_code="INVALID_DESTINATION_LABEL",
                    remediation=(
                        "destination_label には現在の状況に表示された S1, S2 等の "
                        "ラベル、またはスポット名 (例: 閲覧室) を指定してください。"
                    ),
                )
            destination_id = self.runtime.id_mapper.get_str("spot", target.spot_id)
            self.runtime.do_move(player_id, destination_id)
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message=f"{target.display_name}へ移動しました。",
                ),
            )

        if name == TOOL_NAME_SPOT_GRAPH_INTERACT:
            label = str(arguments.get("object_label", ""))
            action_name = str(arguments.get("action_name", ""))
            target = targets.get(label)
            if target is None or target.world_object_id is None:
                # F1: 失敗時に有効ラベルを列挙。Issue #154 デモで Gemma 4 /
                # gpt-5-mini ともに ``object_label="操作盤"`` (display name)
                # を使い続けて同じ失敗を繰り返した。実際には ``OBJ1`` が
                # 正しい label。message で valid 一覧を見せて次の試行で
                # 正しい値が選べるようにする。
                valid_objects = _list_object_labels(targets)
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        f"オブジェクトラベルが見つかりません: {label}。"
                        f"有効な object_label: {valid_objects or '(この場所に interactable なオブジェクトなし)'}"
                    ),
                    error_code="INVALID_TARGET_LABEL",
                    remediation=(
                        "object_label には現在の状況に表示された OBJ1, OBJ2 等の "
                        "ラベル (display name ではなく) を指定してください。"
                    ),
                )
            object_id = self.runtime.id_mapper.get_str("object", target.world_object_id)
            result = self.runtime.do_interact(player_id, object_id, action_name)
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message="; ".join(result.messages) if result.messages else "完了",
                ),
            )

        if name == TOOL_NAME_SPOT_GRAPH_LISTEN:
            # tool catalog に LISTEN_DEFINITION があるのに dispatch が無く
            # UNSUPPORTED_TOOL に化けていた配線漏れ (Issue #154 デモで観測) を
            # 修正。runtime.do_listen が SpotSoundHeardEvent を発火し、
            # observation pipeline で本人にだけ観測が届く (formatter が prose
            # を構築するので、ここでは件数ベースのサマリだけ返す)。
            try:
                event_count = self.runtime.do_listen(player_id)
            except Exception as exc:
                logger.exception(
                    "do_listen failed for player=%s", player_id.value
                )
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        "耳を澄ますに失敗しました。"
                    ),
                    error_code="LLM_TOOL_EXECUTION_FAILED",
                    remediation="やり直すか別のツールを使ってください。",
                )
            if event_count == 0:
                base_message = "耳を澄ましたが、何も聞こえなかった。"
            elif event_count == 1:
                base_message = "耳を澄ました。周囲の音が観測として届いた。"
            else:
                base_message = (
                    f"耳を澄ました。{event_count} 箇所からの音が観測として届いた。"
                )
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(success=True, message=base_message),
            )

        if name == TOOL_NAME_SPOT_GRAPH_WAIT:
            reason = str(arguments.get("reason", "")).strip()
            tick = self.runtime.do_wait(player_id, reason=reason)
            suffix = f"（理由: {reason}）" if reason else ""
            return with_inner_thought_empty_warning(
                name,
                arguments,
                LlmCommandResultDto(
                    success=True,
                    message=f"待機して時間が進んだ: tick={tick}{suffix}",
                ),
            )

        if name == TOOL_NAME_SAY:
            content = str(arguments.get("content", "")).strip()
            if not content:
                return LlmCommandResultDto(
                    success=False,
                    message="発言内容が空です。",
                    error_code="INVALID_SPEECH_CONTENT",
                )
            # PR 2 (#227): _append_agent_speech (全プレイヤー broadcast) を廃止し、
            # PlayerSpeechApplicationService 経由で PlayerSpokeEvent を fire する。
            # 距離 gating (SoundPropagationService) は recipient strategy 側で行われる。
            self.runtime.do_say(player_id, content)
            return LlmCommandResultDto(success=True, message=f"発言した: {content}")

        if name == TOOL_NAME_WHISPER:
            content = str(arguments.get("content", "")).strip()
            target_label = str(arguments.get("target_label", ""))
            target = targets.get(target_label)
            if not content or target is None or target.player_id is None:
                # F1: 失敗時の診断性向上。content 空 / 宛先未解決のどちらの
                # 失敗かを明示し、宛先 (player) 候補を列挙する。
                if not content:
                    detail = "content が空です。"
                else:
                    valid_players = _list_player_labels(targets)
                    detail = (
                        f"target_label={target_label!r} が見つかりません。"
                        f"有効な target_label: {valid_players or '(同 spot に他プレイヤーなし)'}"
                    )
                return LlmCommandResultDto(
                    success=False,
                    message=f"囁きを送れませんでした: {detail}",
                    error_code="INVALID_WHISPER",
                    remediation=(
                        "target_label には現在の状況に表示された P1, P2 等の "
                        "ラベル (display name ではなく) を指定してください。"
                    ),
                )
            # PR 2 (#227): _append_agent_speech を廃止し、PlayerSpeechApplicationService
            # 経由で PlayerSpokeEvent (WHISPER channel) を fire する。
            self.runtime.do_whisper(
                player_id,
                content,
                PlayerId(target.player_id),
            )
            return LlmCommandResultDto(success=True, message=f"囁いた: {content}")

        if name == TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION:
            return LlmCommandResultDto(
                success=False,
                message="サブロケーション変更は脱出ランタイムでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
            )

        # NOTE: pure_spot_graph mode (B-4 / Issue #155) では TODO ツールは LLM
        # の tools リストに含まれないため、このディスパッチは通常到達しない。
        # 安全側のフォールバックとして残してあるだけで、deletion 候補ではない。
        if name in (
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_TODO_COMPLETE,
        ):
            return self.runtime.run_llm_auxiliary_tool(player_id, name, arguments)

        return LlmCommandResultDto(
            success=False,
            message=f"未対応のツールです: {name}",
            error_code="UNSUPPORTED_TOOL",
        )

    def _time_label(self) -> str:
        tick = self.runtime.current_tick()
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        return f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"


@dataclass
class _SessionState:
    """Lightweight bookkeeping for a running game session."""

    session_id: str
    world_id: str
    world_title: str
    character_ids: list[str]
    status: str  # "running" | "paused" | "ended"
    created_at: str
    speed_multiplier: float = 1.0

    runtime: Any = field(default=None, repr=False)
    llm_wiring: Any = field(default=None, repr=False)
    pending_llm_turns: set[int] = field(default_factory=set, repr=False)


@dataclass
class GameRuntimeManager:
    """Facade consumed by all API routers."""

    scenarios_dir: Path = field(default_factory=lambda: Path("data/scenarios"))
    characters_path: Path = field(default_factory=lambda: Path("data/characters.json"))

    _scenario_cache: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _characters: Dict[str, CharacterDetailResponse] = field(
        default_factory=dict, repr=False
    )
    _characters_loaded: bool = field(default=False, repr=False)
    _sessions: Dict[str, _SessionState] = field(
        default_factory=dict, repr=False
    )
    _chat_histories: Dict[str, list[ChatMessageResponse]] = field(
        default_factory=dict, repr=False
    )

    # ── Worlds ──

    def _load_scenario_raw(self, world_id: str) -> Optional[Dict[str, Any]]:
        if world_id in self._scenario_cache:
            return self._scenario_cache[world_id]
        path = self.scenarios_dir / f"{world_id}.json"
        if not path.exists():
            return None
        raw = _read_scenario_metadata(path)
        if raw is not None:
            self._scenario_cache[world_id] = raw
        return raw

    def list_available_worlds(self) -> list[WorldSummaryResponse]:
        worlds: list[WorldSummaryResponse] = []
        if not self.scenarios_dir.exists():
            return worlds
        for path in sorted(self.scenarios_dir.glob("*.json")):
            raw = self._load_scenario_raw(path.stem)
            if raw is None:
                continue
            meta = raw.get("metadata", {})
            worlds.append(
                WorldSummaryResponse(
                    id=meta.get("id", path.stem),
                    title=meta.get("title", path.stem),
                    description=meta.get("description", ""),
                    theme=meta.get("theme", ""),
                    difficulty=meta.get("difficulty", "medium"),
                    estimated_ticks=int(meta.get("estimated_ticks", 100)),
                    tags=list(meta.get("tags", [])),
                )
            )
        return worlds

    def get_world_detail(self, world_id: str) -> Optional[WorldDetailResponse]:
        raw = self._load_scenario_raw(world_id)
        if raw is None:
            return None
        meta = raw.get("metadata", {})
        return WorldDetailResponse(
            id=meta.get("id", world_id),
            title=meta.get("title", world_id),
            description=meta.get("description", ""),
            theme=meta.get("theme", ""),
            difficulty=meta.get("difficulty", "medium"),
            estimated_ticks=int(meta.get("estimated_ticks", 100)),
            tags=list(meta.get("tags", [])),
            spots_count=len(raw.get("spots", [])),
            items_count=len(raw.get("item_specs", [])),
            connections_count=len(raw.get("connections", [])),
        )

    # ── Characters ──

    def _load_characters(self) -> None:
        if self._characters_loaded:
            return
        self._characters_loaded = True
        if not self.characters_path.exists():
            self._characters = {}
            return
        try:
            with open(self.characters_path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read characters %s: %s", self.characters_path, exc)
            self._characters = {}
            return

        entries = raw.get("characters", []) if isinstance(raw, dict) else []
        characters: dict[str, CharacterDetailResponse] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                character = CharacterDetailResponse(**entry)
            except Exception as exc:
                logger.warning("Skipping invalid character entry: %s", exc)
                continue
            characters[character.id] = character
        self._characters = characters

    def _save_characters(self) -> None:
        self.characters_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "characters": [
                character.model_dump()
                for character in sorted(
                    self._characters.values(), key=lambda c: c.name
                )
            ]
        }
        tmp_path = self.characters_path.with_suffix(self.characters_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(self.characters_path)

    def list_characters(self) -> list[CharacterSummaryResponse]:
        self._load_characters()
        return [
            CharacterSummaryResponse(
                id=character.id,
                name=character.name,
                age_image=character.age_image,
                personality_tags=character.personality_tags,
                portrait_url=character.portrait_url,
                icon_url=character.icon_url,
            )
            for character in sorted(self._characters.values(), key=lambda c: c.name)
        ]

    def get_character(self, character_id: str) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        return self._characters.get(character_id)

    def create_character(
        self, request: CharacterCreateRequest
    ) -> CharacterDetailResponse:
        self._load_characters()
        cid = uuid.uuid4().hex[:8]
        while cid in self._characters:
            cid = uuid.uuid4().hex[:8]
        character = CharacterDetailResponse(
            id=cid,
            name=request.name,
            personality_tags=request.personality_tags,
            first_person=request.first_person,
            appearance=request.appearance,
            speech_samples=request.speech_samples,
            fragmented_memory=request.fragmented_memory,
            values=request.values,
            strengths=request.strengths,
            weaknesses=request.weaknesses,
            interpersonal_tendency=request.interpersonal_tendency,
            behavioral_rules=list(request.behavioral_rules or ()),
        )
        self._characters[cid] = character
        self._save_characters()
        return character

    def update_character(
        self, character_id: str, request: CharacterUpdateRequest
    ) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        current = self._characters.get(character_id)
        if current is None:
            return None
        data = current.model_dump()
        update_data = request.model_dump(exclude_unset=True)
        data.update({key: value for key, value in update_data.items() if value is not None})
        updated = CharacterDetailResponse(**data)
        self._characters[character_id] = updated
        self._save_characters()
        return updated

    # ── Sessions ──

    def create_session(
        self, request: SessionCreateRequest
    ) -> SessionSummaryResponse:
        scenario_path = self.scenarios_dir / f"{request.world_id}.json"
        if not scenario_path.exists():
            raise ValueError(f"World not found: {request.world_id}")

        from demos.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        escape_character = None
        if request.character_ids:
            detail = self.get_character(request.character_ids[0])
            escape_character = _character_to_escape_prompt_input(detail)

        runtime = create_escape_game_runtime(
            scenario_path, escape_character=escape_character
        )
        spawn_ids = frozenset(int(sp.player_id) for sp in runtime.scenario.player_spawns)
        llm_resolver = _EscapeSpawnAllPlayersLlmResolver(spawn_player_ids=spawn_ids)
        # appender / turn_scheduler は heartbeat と ActionFailed の両方で
        # 共有する (同じ observation buffer に書き込み、同じ turn trigger を
        # 呼ぶため)。
        appender = ObservationAppender(runtime._obs_buffer)
        # 注意: llm_wiring を構築する前に turn_scheduler を作る必要がある
        # ため、最初に空の wiring を作り、それから scheduler / emitter を
        # 組み立てて wiring に注入する流れにする。
        llm_wiring = _EscapeGameLlmWiring(
            runtime=runtime, observation_buffer=runtime._obs_buffer
        )
        turn_scheduler = ObservationTurnScheduler(
            turn_trigger=llm_wiring.llm_turn_trigger,
            llm_player_resolver=llm_resolver,
        )

        def _heartbeat_llm_player_ids() -> Iterable[PlayerId]:
            return tuple(PlayerId(int(sp.player_id)) for sp in runtime.scenario.player_spawns)

        heartbeat_emitter = HeartbeatObservationEmitter(
            appender,
            turn_scheduler,
            _heartbeat_llm_player_ids,
        )
        # ActionFailed 観測の wire: 失敗 DTO を当該プレイヤーへの観測に変換する。
        # ``intent_id_generator`` は wiring と emitter で共有しないが、wiring 側
        # で intent_id を払い出して emitter に渡す形を取る (emitter は受け取った
        # intent をそのまま使う最小役割)。
        action_failed_emitter = ActionFailedObservationEmitter(
            observation_appender=appender,
            turn_scheduler=turn_scheduler,
        )
        llm_wiring.attach_action_failed_wiring(
            emitter=action_failed_emitter,
            generator=IntentIdGenerator(),
        )
        runtime.set_simulation_llm_turn_trigger(llm_wiring.llm_turn_trigger)
        runtime.set_simulation_heartbeat_emitter(heartbeat_emitter)
        # PR 2 (#227): speech 配信は ObservationPipeline 経由になった。受信者が
        # 他者発話を聞いた場合、ObservationTurnScheduler 経由でターンを積む
        # 必要があるため、wiring 完成後の scheduler を runtime に注入する。
        runtime.set_observation_turn_scheduler(turn_scheduler)

        sid = uuid.uuid4().hex[:12]
        title = runtime.metadata.title
        state = _SessionState(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            character_ids=request.character_ids,
            status="running",
            created_at=_utcnow_iso(),
            runtime=runtime,
            llm_wiring=llm_wiring,
        )
        self._sessions[sid] = state
        logger.info("Session %s created for world %s", sid, request.world_id)
        return SessionSummaryResponse(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            status="running",
            current_tick=0,
            character_ids=request.character_ids,
            created_at=state.created_at,
        )

    def get_session_state(
        self, session_id: str
    ) -> Optional[SessionStateResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        runtime = state.runtime
        tick = runtime.current_tick() if runtime else 0
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"{h}:{m:02d}"

        is_ended = False
        end_result = None
        end_reason = None
        if runtime:
            result = runtime.check_game_end()
            is_ended = result.is_ended
            if is_ended:
                end_result = str(result.result) if result.result else None
                end_reason = result.reason
                state.status = "ended"

        return SessionStateResponse(
            session_id=session_id,
            status=state.status,
            current_tick=tick,
            game_time_label=time_label,
            is_ended=is_ended,
            end_result=end_result,
            end_reason=end_reason,
        )

    def pause_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "paused"
        return True

    def resume_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "running"
        return True

    def stop_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "ended"
        return True

    def set_session_speed(
        self, session_id: str, speed_multiplier: float
    ) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.speed_multiplier = speed_multiplier
        return True

    def iter_running_runtimes(self) -> "Iterator[tuple[str, Any]]":
        """Yield ``(session_id, runtime)`` pairs for sessions in 'running' status.

        Used by the background tick loop to advance game time. Skips
        paused/ended sessions and sessions without a runtime (legacy stubs).

        The runtime is typed as ``Any`` because multiple runtime classes
        (escape game, future spot-graph standalone, etc.) share only the
        informal duck-typed ``advance_tick()`` contract.
        """
        for session_id, state in self._sessions.items():
            if state.status != "running" or state.runtime is None:
                continue
            yield session_id, state.runtime

    def run_scheduled_llm_turns(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None or state.llm_wiring is None:
            return False
        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is None or not callable(getattr(turn_trigger, "run_scheduled_turns", None)):
            return False
        turn_trigger.run_scheduled_turns()
        return True

    # ── Observations ──

    def get_spot_view(
        self,
        session_id: str,
        *,
        character_id: Optional[str] = None,
        spot_id: Optional[str] = None,
    ) -> Optional[SpotViewResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = runtime._spot_graph_repo.find_graph()

        if spot_id is not None:
            target_spot_int = runtime.id_mapper.get_int("spot", spot_id)
            from ai_rpg_world.domain.world.value_object.spot_id import SpotId
            target_spot_id = SpotId.create(target_spot_int)
        elif character_id is not None:
            pid_int = runtime.id_mapper.get_int("player", character_id)
            eid = EntityId.create(pid_int)
            target_spot_id = graph.get_entity_spot(eid)
        else:
            first_spawn = runtime.scenario.player_spawns[0]
            eid = EntityId.create(first_spawn.player_id)
            target_spot_id = graph.get_entity_spot(eid)

        spot_node = graph.get_spot(target_spot_id)
        interior = runtime._spot_interior_repo.find_by_spot_id(target_spot_id)

        characters: list[CharacterInSpotResponse] = []
        presence = graph.presence_at(target_spot_id)
        for eid_val in presence.present_entity_ids:
            eid_int = eid_val.value if hasattr(eid_val, "value") else int(eid_val)
            name = runtime.get_player_name(PlayerId(eid_int))
            spawn = next(
                (s for s in runtime.scenario.player_spawns if s.player_id == eid_int),
                None,
            )
            str_id = spawn.string_id if spawn else str(eid_val)
            characters.append(CharacterInSpotResponse(
                character_id=str_id,
                name=name,
            ))

        objects: list[SpotObjectResponse] = []
        if interior:
            for obj in interior.objects:
                actions = [i.action_name for i in obj.interactions]
                obj_str = _safe_get_str(runtime.id_mapper, "object", obj.object_id.value)
                objects.append(SpotObjectResponse(
                    object_id=obj_str,
                    name=obj.name,
                    description=obj.description,
                    object_type=obj.object_type.name,
                    state=dict(obj.state),
                    available_actions=actions,
                ))

        connections: list[SpotConnectionResponse] = []
        for conn in graph.iter_outgoing_connections_from(target_spot_id):
            target_node = graph.get_spot(conn.to_spot_id)
            conn_str = _safe_get_str(runtime.id_mapper, "connection", conn.connection_id.value)
            connections.append(SpotConnectionResponse(
                connection_id=conn_str,
                target_spot_id=_safe_get_str(runtime.id_mapper, "spot", conn.to_spot_id.value),
                target_spot_name=target_node.name,
                name=conn.name,
                is_passable=conn.passage.traversable,
            ))

        spot_str = _safe_get_str(runtime.id_mapper, "spot", target_spot_id.value)
        return SpotViewResponse(
            spot_id=spot_str,
            spot_name=spot_node.name,
            spot_description=spot_node.description,
            background_image_key=spot_str,
            atmosphere={
                "lighting": spot_node.atmosphere.lighting.name,
                "sound_ambient": spot_node.atmosphere.sound_ambient,
                "temperature": spot_node.atmosphere.temperature.name,
                "smell": spot_node.atmosphere.smell,
            } if spot_node.atmosphere else None,
            characters_present=characters,
            objects=objects,
            connections=connections,
        )

    def get_event_log(
        self, session_id: str, *, limit: int = 50, offset: int = 0
    ) -> Optional[EventLogResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return EventLogResponse()

    def get_inventory(
        self, session_id: str, character_id: str
    ) -> Optional[InventoryResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        pid_int = runtime.id_mapper.get_int("player", character_id)
        pid = PlayerId(pid_int)
        inv = runtime._player_inventory_repo.find_by_id(pid)
        items: list[InventoryItemResponse] = []
        if inv:
            from ai_rpg_world.domain.player.value_object.slot_id import SlotId

            counts: dict[int, int] = {}
            specs: dict[int, Any] = {}
            for slot_idx in range(inv._max_slots):
                iid = inv.get_item_instance_id_by_slot(SlotId(slot_idx))
                if iid is None:
                    continue
                item = runtime._item_repo.find_by_id(iid)
                if item is None:
                    continue
                sid = item.item_spec.item_spec_id.value
                counts[sid] = counts.get(sid, 0) + 1
                if sid not in specs:
                    specs[sid] = item.item_spec
            for sid, spec in specs.items():
                spec_str = _safe_get_str(runtime.id_mapper, "item_spec", sid)
                items.append(InventoryItemResponse(
                    item_spec_id=spec_str,
                    name=spec.name,
                    description=spec.description,
                    quantity=counts[sid],
                ))

        return InventoryResponse(character_id=character_id, items=items)

    # ── Chat (stub) ──

    def send_chat_message(
        self, request: ChatSendRequest
    ) -> ChatMessageResponse:
        if request.scope != "individual":
            raise ValueError("Only individual chat scope is currently supported")

        state = self._sessions.get(request.session_id)
        if state is None:
            raise ValueError(f"Session not found: {request.session_id}")
        if state.runtime is None:
            raise ValueError(f"Session has no active runtime: {request.session_id}")

        runtime = state.runtime

        try:
            target_player_int = runtime.id_mapper.get_int(
                "player", request.target_character_id
            )
        except (ScenarioIdMappingError, KeyError):
            try:
                character_index = state.character_ids.index(request.target_character_id)
                target_player_int = runtime.get_player_ids()[character_index].value
            except (ValueError, IndexError) as exc:
                raise ValueError(
                    f"Character not found in session: {request.target_character_id}"
                ) from exc

        target_player_id = PlayerId(target_player_int)
        now = datetime.now(timezone.utc)
        tick = runtime.current_tick() if callable(getattr(runtime, "current_tick", None)) else 0
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"

        output = ObservationOutput(
            prose=f"どこからか、あなたに向けた声が届いた: 「{request.message}」",
            structured={
                "type": "user_directed_speech",
                "speaker": "user",
                "target_character_id": request.target_character_id,
                "content": request.message,
                "channel": "direct",
            },
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

        appender = getattr(state.llm_wiring, "observation_appender", None)
        if appender is None:
            buffer = getattr(runtime, "_obs_buffer", None)
            if buffer is None:
                raise ValueError("Session runtime does not expose an observation buffer")
            appender = ObservationAppender(buffer)
        appender.append(target_player_id, output, now, time_label)

        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is not None:
            turn_trigger.schedule_turn(target_player_id)
        else:
            state.pending_llm_turns.add(target_player_id.value)

        message = ChatMessageResponse(
            sender="player",
            message=request.message,
            timestamp=_utcnow_iso(),
            is_player=True,
        )
        key = f"{request.session_id}:{request.target_character_id}"
        self._chat_histories.setdefault(key, []).append(message)
        self._chat_histories.setdefault(request.target_character_id, []).append(message)
        return message

    def get_chat_history(
        self, character_id: str
    ) -> Optional[ChatHistoryResponse]:
        return ChatHistoryResponse(
            messages=list(self._chat_histories.get(character_id, []))
        )

    # ── Results (stub) ──

    def get_result_impressions(
        self, session_id: str
    ) -> Optional[ResultImpressionResponse]:
        return None

    def get_result_timeline(
        self, session_id: str
    ) -> Optional[ResultTimelineResponse]:
        return None

    def get_result_relationships(
        self, session_id: str
    ) -> Optional[ResultRelationshipResponse]:
        return None

    # ── Saves (stub) ──

    def list_saves(self) -> SaveListResponse:
        return SaveListResponse()

    def save_session(self, session_id: str) -> Optional[SaveSlotResponse]:
        return None

    def load_save(self, save_id: str) -> Optional[SaveSlotResponse]:
        return None

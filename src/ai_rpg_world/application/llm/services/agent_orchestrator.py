"""
LLM エージェントの 1 ターン実行を統合するオーケストレータ。

プロンプト組み立て → LLM 呼び出し → tool_call 取得 → コマンド実行 → 結果を IActionResultStore に記録。
"""

import json
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    is_reschedulable_error_code,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ILLMClient,
    IPromptBuilder,
    IToolArgumentResolver,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.result_summary_builder import build_result_summary
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    SUBJECTIVE_ACTION_TEXT_FIELDS,
    is_subjective_action_tool,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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
) -> None:
    """行動結果を IActionResultStore に記録する（失敗メタ・引数フィンガープリント付き）。"""
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
        self._prompt_builder = prompt_builder
        self._llm_client = llm_client
        self._tool_command_mapper = tool_command_mapper
        self._action_result_store = action_result_store
        self._tool_argument_resolver = (
            tool_argument_resolver
            if tool_argument_resolver is not None
            else DefaultToolArgumentResolver()
        )

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        """
        1 ターン実行: プロンプト組み立て → LLM 呼び出し → tool_call を実行 → 結果を store に記録。
        戻り値はそのターンの実行結果（LlmCommandResultDto）。
        tool_call が無い場合は「ツール未選択」として store に記録し、対応する DTO を返す。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")

        return self._run_turn_core(player_id)

    def _run_turn_core(self, player_id: PlayerId) -> LlmCommandResultDto:
        request = self._prompt_builder.build(player_id)
        messages = request["messages"]
        tools = request["tools"]
        tool_choice = request.get("tool_choice", "required")
        runtime_context = request.get("tool_runtime_context")
        if not isinstance(runtime_context, ToolRuntimeContextDto):
            runtime_context = ToolRuntimeContextDto.empty()

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
            )
            return result_dto

        result_dto = self._tool_command_mapper.execute(
            player_id.value,
            name,
            canonical_arguments,
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
            fingerprint_args=canonical_arguments,
        )
        return result_dto

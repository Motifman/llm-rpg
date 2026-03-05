"""
LLM エージェントの 1 ターン実行を統合するオーケストレータ。

プロンプト組み立て → LLM 呼び出し → tool_call 取得 → コマンド実行 → 結果を IActionResultStore に記録。
"""

import json
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ILLMClient,
    IPromptBuilder,
)
from ai_rpg_world.application.llm.result_summary_builder import build_result_summary
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
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
    ) -> None:
        if not isinstance(prompt_builder, IPromptBuilder):
            raise TypeError("prompt_builder must be IPromptBuilder")
        if not isinstance(llm_client, ILLMClient):
            raise TypeError("llm_client must be ILLMClient")
        if not isinstance(tool_command_mapper, ToolCommandMapper):
            raise TypeError("tool_command_mapper must be ToolCommandMapper")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        self._prompt_builder = prompt_builder
        self._llm_client = llm_client
        self._tool_command_mapper = tool_command_mapper
        self._action_result_store = action_result_store

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        """
        1 ターン実行: プロンプト組み立て → LLM 呼び出し → tool_call を実行 → 結果を store に記録。
        戻り値はそのターンの実行結果（LlmCommandResultDto）。
        tool_call が無い場合は「ツール未選択」として store に記録し、対応する DTO を返す。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")

        request = self._prompt_builder.build(player_id)
        messages = request["messages"]
        tools = request["tools"]
        tool_choice = request.get("tool_choice", "required")

        tool_call = self._llm_client.invoke(messages, tools, tool_choice)

        if tool_call is None:
            action_summary = "ツールが選択されませんでした。"
            result_dto = LlmCommandResultDto(
                success=False,
                message="LLM がツールを返しませんでした。",
                error_code="NO_TOOL_CALL",
                remediation="必ずいずれか 1 つのツールを呼び出してください。",
            )
            result_summary = build_result_summary(result_dto)
            self._action_result_store.append(player_id, action_summary, result_summary)
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

        result_dto = self._tool_command_mapper.execute(
            player_id.value,
            name,
            arguments,
        )
        action_summary = _format_action_summary(name, arguments)
        result_summary = build_result_summary(result_dto)
        self._action_result_store.append(player_id, action_summary, result_summary)
        return result_dto

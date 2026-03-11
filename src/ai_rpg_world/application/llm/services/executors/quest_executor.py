"""
Quest ツール（accept, cancel, approve）の実行。

ToolCommandMapper のサブマッパーとして、クエスト関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_APPROVE,
    TOOL_NAME_QUEST_CANCEL,
    TOOL_NAME_QUEST_ISSUE,
)
from ai_rpg_world.application.quest.contracts.commands import (
    AcceptQuestCommand,
    ApproveQuestCommand,
    CancelQuestCommand,
    IssueQuestCommand,
)


class QuestToolExecutor:
    """
    Quest ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(self, quest_service: Optional[Any] = None) -> None:
        self._quest_service = quest_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。quest_service が None の場合は空辞書。"""
        if self._quest_service is None:
            return {}
        return {
            TOOL_NAME_QUEST_ACCEPT: self._execute_quest_accept,
            TOOL_NAME_QUEST_CANCEL: self._execute_quest_cancel,
            TOOL_NAME_QUEST_APPROVE: self._execute_quest_approve,
            TOOL_NAME_QUEST_ISSUE: self._execute_quest_issue,
        }

    def _execute_quest_accept(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._quest_service is None:
            return unknown_tool("クエスト受託ツールはまだ利用できません。")
        if args.get("quest_id") is None:
            return invalid_arg_result("quest_id")
        try:
            result = self._quest_service.accept_quest(
                AcceptQuestCommand(quest_id=int(args["quest_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_quest_cancel(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._quest_service is None:
            return unknown_tool("クエストキャンセルツールはまだ利用できません。")
        if args.get("quest_id") is None:
            return invalid_arg_result("quest_id")
        try:
            result = self._quest_service.cancel_quest(
                CancelQuestCommand(quest_id=int(args["quest_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_quest_approve(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._quest_service is None:
            return unknown_tool("クエスト承認ツールはまだ利用できません。")
        if args.get("quest_id") is None:
            return invalid_arg_result("quest_id")
        try:
            result = self._quest_service.approve_quest(
                ApproveQuestCommand(
                    quest_id=int(args["quest_id"]), approver_player_id=player_id
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_quest_issue(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._quest_service is None:
            return unknown_tool("クエスト発行ツールはまだ利用できません。")
        if args.get("objectives") is None or not args.get("objectives"):
            return invalid_arg_result("objectives")
        try:
            command = IssueQuestCommand(
                objectives=list(args["objectives"]),
                reward_gold=int(args.get("reward_gold", 0)),
                reward_exp=int(args.get("reward_exp", 0)),
                reward_items=args.get("reward_items"),
                issuer_player_id=player_id,
                guild_id=args.get("guild_id"),
            )
            result = self._quest_service.issue_quest(command)
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

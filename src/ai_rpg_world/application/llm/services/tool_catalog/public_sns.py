"""公開SNSの入口は読む・発信する二つだけにする。"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SNS_PUBLISH, TOOL_NAME_SNS_READ


def _build_public_sns_definitions() -> list[ToolDefinitionDto]:
    return [
        ToolDefinitionDto(
            name=TOOL_NAME_SNS_READ,
            description="公開SNSの受信箱・投稿一覧・投稿と返信を読みます。表示は次に読み直すか閉じるまで残ります。",
            parameters={
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "enum": ["inbox", "posts", "thread", "close"],
                        "description": "読む画面。closeは現在の画面を閉じます。",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "threadで読む投稿または返信の、表示された対象識別子。",
                    },
                    "cursor": {"type": "string", "description": "同じ画面の続きとして表示された値。"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "一度に読む件数。省略時は10件。",
                    },
                },
                "required": ["view"],
            },
        ),
        ToolDefinitionDto(
            name=TOOL_NAME_SNS_PUBLISH,
            description="公開SNSに新しい投稿をするか、表示された投稿・返信へ返信します。事前の閲覧は必須ではありません。",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["new", "reply"],
                        "description": "newは新規投稿、replyは対象への返信。",
                    },
                    "content": {"type": "string", "maxLength": 280, "description": "公開する本文。"},
                    "target_id": {
                        "type": "string",
                        "description": "replyで返信する投稿または返信の、通知や画面に表示された対象識別子。",
                    },
                },
                "required": ["action", "content"],
            },
        ),
    ]


SNS_READ_DEFINITION, SNS_PUBLISH_DEFINITION = _build_public_sns_definitions()


def get_public_sns_definitions() -> list[ToolDefinitionDto]:
    return [SNS_READ_DEFINITION, SNS_PUBLISH_DEFINITION]

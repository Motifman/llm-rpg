"""SNS 系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    SnsToolAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_BLOCK,
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_LIKE_REPLY,
    TOOL_NAME_SNS_SUBSCRIBE,
    TOOL_NAME_SNS_UNBLOCK,
    TOOL_NAME_SNS_UNFOLLOW,
    TOOL_NAME_SNS_UNSUBSCRIBE,
)

SNS_CREATE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "投稿する内容（280文字以内）。"},
        "visibility": {
            "type": "string",
            "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。",
        },
    },
    "required": ["content"],
}
SNS_CREATE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_POST,
    description="SNSに新しい投稿を作成します。",
    parameters=SNS_CREATE_POST_PARAMETERS,
)

SNS_CREATE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "リプライする内容。"},
        "parent_post_id": {"type": "integer", "description": "親ポストのID。parent_reply_id とどちらか必須。"},
        "parent_reply_id": {"type": "integer", "description": "親リプライのID。parent_post_id とどちらか必須。"},
        "visibility": {
            "type": "string",
            "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。",
        },
    },
    "required": ["content"],
}
SNS_CREATE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_REPLY,
    description="ポストまたはリプライに返信します。parent_post_id または parent_reply_id のどちらかを指定してください。",
    parameters=SNS_CREATE_REPLY_PARAMETERS,
)

SNS_LIKE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "post_id": {"type": "integer", "description": "いいねするポストのID。"},
    },
    "required": ["post_id"],
}
SNS_LIKE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_POST,
    description="ポストにいいねします。",
    parameters=SNS_LIKE_POST_PARAMETERS,
)

SNS_LIKE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "reply_id": {"type": "integer", "description": "いいねするリプライのID。"},
    },
    "required": ["reply_id"],
}
SNS_LIKE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_REPLY,
    description="リプライにいいねします。",
    parameters=SNS_LIKE_REPLY_PARAMETERS,
)

SNS_FOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォローするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_FOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_FOLLOW,
    description="指定したユーザーをフォローします。",
    parameters=SNS_FOLLOW_PARAMETERS,
)

SNS_UNFOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォロー解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNFOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNFOLLOW,
    description="指定したユーザーのフォローを解除します。",
    parameters=SNS_UNFOLLOW_PARAMETERS,
)

SNS_SUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_SUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_SUBSCRIBE,
    description="指定したユーザーをサブスクライブします。",
    parameters=SNS_SUBSCRIBE_PARAMETERS,
)

SNS_UNSUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブ解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNSUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNSUBSCRIBE,
    description="指定したユーザーのサブスクライブを解除します。",
    parameters=SNS_UNSUBSCRIBE_PARAMETERS,
)

SNS_BLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロックするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_BLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_BLOCK,
    description="指定したユーザーをブロックします。",
    parameters=SNS_BLOCK_PARAMETERS,
)

SNS_UNBLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロック解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNBLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNBLOCK,
    description="指定したユーザーのブロックを解除します。",
    parameters=SNS_UNBLOCK_PARAMETERS,
)


def get_sns_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """SNS 系ツールの (definition, resolver) 一覧を返す。SNS 全ツールは同一 resolver を共有。"""
    sns_resolver = SnsToolAvailabilityResolver()
    return [
        (SNS_CREATE_POST_DEFINITION, sns_resolver),
        (SNS_CREATE_REPLY_DEFINITION, sns_resolver),
        (SNS_LIKE_POST_DEFINITION, sns_resolver),
        (SNS_LIKE_REPLY_DEFINITION, sns_resolver),
        (SNS_FOLLOW_DEFINITION, sns_resolver),
        (SNS_UNFOLLOW_DEFINITION, sns_resolver),
        (SNS_SUBSCRIBE_DEFINITION, sns_resolver),
        (SNS_UNSUBSCRIBE_DEFINITION, sns_resolver),
        (SNS_BLOCK_DEFINITION, sns_resolver),
        (SNS_UNBLOCK_DEFINITION, sns_resolver),
    ]


__all__ = [
    "get_sns_specs",
]

"""ギルド系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    GuildAddMemberAvailabilityResolver,
    GuildChangeRoleAvailabilityResolver,
    GuildCreateAvailabilityResolver,
    GuildDepositBankAvailabilityResolver,
    GuildDisbandAvailabilityResolver,
    GuildLeaveAvailabilityResolver,
    GuildWithdrawBankAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
)

GUILD_CREATE_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "ギルド名。"},
        "description": {"type": "string", "description": "ギルドの説明。", "default": ""},
    },
    "required": ["name"],
}
GUILD_CREATE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_CREATE,
    description="現在地のロケーションにギルドを作成します。spot_id と location_area_id は現在地から自動取得されます。",
    parameters=GUILD_CREATE_PARAMETERS,
)

GUILD_ADD_MEMBER_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "招待先ギルドラベル（例: G1）。"},
        "target_player_label": {"type": "string", "description": "招待するプレイヤーラベル（例: P1）。"},
    },
    "required": ["guild_label", "target_player_label"],
}
GUILD_ADD_MEMBER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_ADD_MEMBER,
    description="ギルドにプレイヤーを招待します（オフィサー以上）。",
    parameters=GUILD_ADD_MEMBER_PARAMETERS,
)

GUILD_CHANGE_ROLE_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "対象ギルドラベル（例: G1）。"},
        "target_member_label": {"type": "string", "description": "役職変更するメンバーラベル（例: GM1）。"},
        "new_role": {
            "type": "string",
            "description": "新しい役職。leader / officer / member のいずれか。",
            "enum": ["leader", "officer", "member"],
        },
    },
    "required": ["guild_label", "target_member_label", "new_role"],
}
GUILD_CHANGE_ROLE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_CHANGE_ROLE,
    description="ギルドメンバーの役職を変更します（オフィサー以上）。",
    parameters=GUILD_CHANGE_ROLE_PARAMETERS,
)

GUILD_DISBAND_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "解散するギルドラベル（例: G1）。"},
    },
    "required": ["guild_label"],
}
GUILD_DISBAND_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_DISBAND,
    description="ギルドを解散します（リーダーのみ）。",
    parameters=GUILD_DISBAND_PARAMETERS,
)

GUILD_LEAVE_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "脱退するギルドラベル（例: G1）。"},
    },
    "required": ["guild_label"],
}
GUILD_LEAVE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_LEAVE,
    description="所属ギルドから脱退します。",
    parameters=GUILD_LEAVE_PARAMETERS,
)

GUILD_DEPOSIT_BANK_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "入金先ギルドラベル（例: G1）。"},
        "amount": {"type": "integer", "description": "入金するゴールド量。"},
    },
    "required": ["guild_label", "amount"],
}
GUILD_DEPOSIT_BANK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_DEPOSIT_BANK,
    description="ギルド金庫にゴールドを入金します。",
    parameters=GUILD_DEPOSIT_BANK_PARAMETERS,
)

GUILD_WITHDRAW_BANK_PARAMETERS = {
    "type": "object",
    "properties": {
        "guild_label": {"type": "string", "description": "出金元ギルドラベル（例: G1）。"},
        "amount": {"type": "integer", "description": "出金するゴールド量。"},
    },
    "required": ["guild_label", "amount"],
}
GUILD_WITHDRAW_BANK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_GUILD_WITHDRAW_BANK,
    description="ギルド金庫からゴールドを出金します（オフィサー以上）。",
    parameters=GUILD_WITHDRAW_BANK_PARAMETERS,
)


def get_guild_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """ギルド系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (GUILD_CREATE_DEFINITION, GuildCreateAvailabilityResolver()),
        (GUILD_ADD_MEMBER_DEFINITION, GuildAddMemberAvailabilityResolver()),
        (GUILD_CHANGE_ROLE_DEFINITION, GuildChangeRoleAvailabilityResolver()),
        (GUILD_DISBAND_DEFINITION, GuildDisbandAvailabilityResolver()),
        (GUILD_LEAVE_DEFINITION, GuildLeaveAvailabilityResolver()),
        (GUILD_DEPOSIT_BANK_DEFINITION, GuildDepositBankAvailabilityResolver()),
        (GUILD_WITHDRAW_BANK_DEFINITION, GuildWithdrawBankAvailabilityResolver()),
    ]


__all__ = [
    "get_guild_specs",
]

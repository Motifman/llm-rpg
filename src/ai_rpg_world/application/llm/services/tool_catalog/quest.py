"""クエスト系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    QuestAcceptAvailabilityResolver,
    QuestApproveAvailabilityResolver,
    QuestCancelAvailabilityResolver,
    QuestIssueAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_APPROVE,
    TOOL_NAME_QUEST_CANCEL,
    TOOL_NAME_QUEST_ISSUE,
)

QUEST_ACCEPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "受託するクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}

QUEST_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_ACCEPT,
    description="掲示されているクエストを受託します。",
    parameters=QUEST_ACCEPT_PARAMETERS,
)

QUEST_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "キャンセルするクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}

QUEST_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_CANCEL,
    description="受託中のクエストをキャンセルします。",
    parameters=QUEST_CANCEL_PARAMETERS,
)

QUEST_APPROVE_PARAMETERS = {
    "type": "object",
    "properties": {
        "quest_label": {"type": "string", "description": "承認するクエストラベル（例: Q1）。"},
    },
    "required": ["quest_label"],
}

QUEST_APPROVE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_APPROVE,
    description="ギルド掲示のクエストを承認します（オフィサー以上）。",
    parameters=QUEST_APPROVE_PARAMETERS,
)

QUEST_ISSUE_PARAMETERS = {
    "type": "object",
    "properties": {
        "objectives": {
            "type": "array",
            "description": "クエスト目標のリスト。target_name または target_id のいずれかを指定。target_name はモンスター名・スポット名・アイテム名・プレイヤー名で検索。",
            "items": {
                "type": "object",
                "properties": {
                    "objective_type": {
                        "type": "string",
                        "description": "kill_monster, obtain_item, reach_spot, kill_player（名前解決対応）。talk_to_npc 等は target_id で指定。",
                    },
                    "target_name": {
                        "type": "string",
                        "description": "目標の名前（ゴブリン、北の森、鉄の剣、プレイヤー名 等）。target_id の代わりに指定可能。",
                    },
                    "target_id": {
                        "type": "integer",
                        "description": "目標の ID（モンスター種別、NPC ID、スポット ID 等）。target_name の代わりに指定可能。",
                    },
                    "required_count": {
                        "type": "integer",
                        "description": "必要数",
                    },
                },
                "required": ["objective_type", "required_count"],
            },
        },
        "reward_gold": {"type": "integer", "description": "報酬ゴールド。", "default": 0},
        "reward_items": {
            "type": "array",
            "description": "報酬アイテム。各要素は item_spec_id と quantity を持つオブジェクト。",
            "items": {
                "type": "object",
                "properties": {
                    "item_spec_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                },
                "required": ["item_spec_id", "quantity"],
            },
        },
        "guild_label": {
            "type": "string",
            "description": "ギルド掲示の場合のギルドラベル（例: G1）。省略時は公開クエスト。ギルド依頼はギルドのロケーションにいる場合のみ発行可能。",
        },
    },
    "required": ["objectives"],
}

QUEST_ISSUE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_QUEST_ISSUE,
    description="クエストを発行します。報酬にゴールド・アイテムを指定可能。guild_label を指定するとギルド掲示（承認待ち）になります。ギルド依頼はギルドのロケーションにいる場合のみ発行可能。",
    parameters=QUEST_ISSUE_PARAMETERS,
)


def get_quest_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """クエスト系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (QUEST_ACCEPT_DEFINITION, QuestAcceptAvailabilityResolver()),
        (QUEST_CANCEL_DEFINITION, QuestCancelAvailabilityResolver()),
        (QUEST_APPROVE_DEFINITION, QuestApproveAvailabilityResolver()),
        (QUEST_ISSUE_DEFINITION, QuestIssueAvailabilityResolver()),
    ]


__all__ = [
    "get_quest_specs",
    "QUEST_ACCEPT_DEFINITION",
    "QUEST_CANCEL_DEFINITION",
    "QUEST_APPROVE_DEFINITION",
    "QUEST_ISSUE_DEFINITION",
]

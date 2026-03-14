"""戦闘・スキル系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    CombatUseSkillAvailabilityResolver,
    SkillAcceptProposalAvailabilityResolver,
    SkillActivateAwakenedModeAvailabilityResolver,
    SkillEquipAvailabilityResolver,
    SkillRejectProposalAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
)

COMBAT_USE_SKILL_PARAMETERS = {
    "type": "object",
    "properties": {
        "skill_label": {
            "type": "string",
            "description": "現在の状況に表示された使用可能スキルラベル（例: K1）。",
        },
        "target_label": {
            "type": "string",
            "description": "攻撃対象ラベル（例: M1, P1）。省略時は自動照準または現在向きを使います。",
        },
    },
    "required": ["skill_label"],
}

COMBAT_USE_SKILL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_COMBAT_USE_SKILL,
    description="使用可能スキルを選んで発動します。対象があればその方向へ向き直ります。",
    parameters=COMBAT_USE_SKILL_PARAMETERS,
)

SKILL_EQUIP_PARAMETERS = {
    "type": "object",
    "properties": {
        "skill_label": {
            "type": "string",
            "description": "装備候補スキルラベル（例: EK1）。",
        },
        "slot_label": {
            "type": "string",
            "description": "装備先スロットラベル（例: ES1）。",
        },
    },
    "required": ["skill_label", "slot_label"],
}

SKILL_EQUIP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_EQUIP,
    description="装備候補スキルを指定したスロットへ装備します。",
    parameters=SKILL_EQUIP_PARAMETERS,
)

SKILL_ACCEPT_PROPOSAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "proposal_label": {
            "type": "string",
            "description": "受諾するスキル提案ラベル（例: SP1）。",
        },
    },
    "required": ["proposal_label"],
}

SKILL_ACCEPT_PROPOSAL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    description="保留中のスキル進化提案を受諾します。",
    parameters=SKILL_ACCEPT_PROPOSAL_PARAMETERS,
)

SKILL_REJECT_PROPOSAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "proposal_label": {
            "type": "string",
            "description": "却下するスキル提案ラベル（例: SP1）。",
        },
    },
    "required": ["proposal_label"],
}

SKILL_REJECT_PROPOSAL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_REJECT_PROPOSAL,
    description="保留中のスキル進化提案を却下します。",
    parameters=SKILL_REJECT_PROPOSAL_PARAMETERS,
)

SKILL_ACTIVATE_AWAKENED_MODE_PARAMETERS = {
    "type": "object",
    "properties": {
        "awakened_action_label": {
            "type": "string",
            "description": "覚醒モード発動ラベル（例: AW1）。",
        },
    },
    "required": ["awakened_action_label"],
}

SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    description="覚醒モードを発動します。継続時間や消費コストはサーバ側設定に従います。",
    parameters=SKILL_ACTIVATE_AWAKENED_MODE_PARAMETERS,
)


def get_combat_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """戦闘・スキル系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (COMBAT_USE_SKILL_DEFINITION, CombatUseSkillAvailabilityResolver()),
        (SKILL_EQUIP_DEFINITION, SkillEquipAvailabilityResolver()),
        (SKILL_ACCEPT_PROPOSAL_DEFINITION, SkillAcceptProposalAvailabilityResolver()),
        (SKILL_REJECT_PROPOSAL_DEFINITION, SkillRejectProposalAvailabilityResolver()),
        (
            SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION,
            SkillActivateAwakenedModeAvailabilityResolver(),
        ),
    ]


__all__ = [
    "get_combat_specs",
    "COMBAT_USE_SKILL_DEFINITION",
    "SKILL_EQUIP_DEFINITION",
    "SKILL_ACCEPT_PROPOSAL_DEFINITION",
    "SKILL_REJECT_PROPOSAL_DEFINITION",
    "SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION",
]

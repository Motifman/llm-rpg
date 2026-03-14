"""戦闘・スキル系ツールの引数解決。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    AwakenedActionToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    SkillEquipCandidateToolRuntimeTargetDto,
    SkillEquipSlotToolRuntimeTargetDto,
    SkillProposalToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target_type,
    resolve_direction_from_context,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
)


class CombatSkillArgumentResolver:
    """戦闘・スキル系ツールの引数解決。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name == TOOL_NAME_COMBAT_USE_SKILL:
            return self._resolve_combat_use_skill(args, runtime_context)
        if tool_name == TOOL_NAME_SKILL_EQUIP:
            return self._resolve_skill_equip(args, runtime_context)
        if tool_name == TOOL_NAME_SKILL_ACCEPT_PROPOSAL:
            return self._resolve_skill_proposal(args, runtime_context)
        if tool_name == TOOL_NAME_SKILL_REJECT_PROPOSAL:
            return self._resolve_skill_proposal(args, runtime_context)
        if tool_name == TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE:
            return self._resolve_activate_awakened_mode(args, runtime_context)
        return None

    def _resolve_combat_use_skill(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        skill_label = args.get("skill_label")
        skill = require_target_type(
            skill_label,
            runtime_context,
            "スキルラベル",
            (SkillToolRuntimeTargetDto,),
        )
        if skill.skill_loadout_id is None or skill.skill_slot_index is None:
            raise ToolArgumentResolutionException(
                f"スキルとして使えないラベルです: {skill_label}",
                "INVALID_TARGET_KIND",
            )
        resolved: Dict[str, Any] = {
            "skill_loadout_id": skill.skill_loadout_id,
            "skill_slot_index": skill.skill_slot_index,
            "skill_display_name": skill.display_name,
            "auto_aim": True,
        }
        target_label = args.get("target_label")
        if target_label is None:
            return resolved
        target = require_target_type(
            target_label,
            runtime_context,
            "攻撃対象ラベル",
            (
                PlayerToolRuntimeTargetDto,
                MonsterToolRuntimeTargetDto,
                NpcToolRuntimeTargetDto,
            ),
        )
        direction = resolve_direction_from_context(target, runtime_context)
        resolved["auto_aim"] = False
        resolved["target_direction"] = direction
        resolved["target_display_name"] = target.display_name
        return resolved

    def _resolve_skill_equip(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        skill_label = args.get("skill_label")
        skill = require_target_type(
            skill_label,
            runtime_context,
            "装備候補スキルラベル",
            (SkillEquipCandidateToolRuntimeTargetDto,),
        )
        slot_label = args.get("slot_label")
        slot = require_target_type(
            slot_label,
            runtime_context,
            "装備先スロットラベル",
            (SkillEquipSlotToolRuntimeTargetDto,),
        )
        if (
            skill.skill_loadout_id is None
            or skill.skill_id is None
            or slot.skill_loadout_id is None
            or slot.deck_tier is None
            or slot.skill_slot_index is None
        ):
            raise ToolArgumentResolutionException(
                "スキル装備に必要な情報が不足しています。",
                "INVALID_TARGET_KIND",
            )
        if skill.skill_loadout_id != slot.skill_loadout_id:
            raise ToolArgumentResolutionException(
                "装備候補スキルと装備先スロットのロードアウトが一致しません。",
                "INVALID_TARGET_KIND",
            )
        return {
            "loadout_id": slot.skill_loadout_id,
            "deck_tier": slot.deck_tier,
            "slot_index": slot.skill_slot_index,
            "skill_id": skill.skill_id,
            "skill_display_name": skill.display_name,
            "slot_display_name": slot.display_name,
        }

    def _resolve_skill_proposal(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        proposal_label = args.get("proposal_label")
        proposal = require_target_type(
            proposal_label,
            runtime_context,
            "スキル提案ラベル",
            (SkillProposalToolRuntimeTargetDto,),
        )
        if proposal.progress_id is None or proposal.proposal_id is None:
            raise ToolArgumentResolutionException(
                f"スキル提案として使えないラベルです: {proposal_label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "progress_id": proposal.progress_id,
            "proposal_id": proposal.proposal_id,
            "proposal_display_name": proposal.display_name,
            "slot_display_name": proposal.target_slot_display_name,
        }

    def _resolve_activate_awakened_mode(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        awakened_label = args.get("awakened_action_label")
        target = require_target_type(
            awakened_label,
            runtime_context,
            "覚醒モード発動ラベル",
            (AwakenedActionToolRuntimeTargetDto,),
        )
        if target.skill_loadout_id is None:
            raise ToolArgumentResolutionException(
                f"覚醒モード発動に使えないラベルです: {awakened_label}",
                "INVALID_TARGET_KIND",
            )
        return {"loadout_id": target.skill_loadout_id}

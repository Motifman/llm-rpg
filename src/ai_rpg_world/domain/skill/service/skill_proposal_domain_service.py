import random
from typing import List

from ai_rpg_world.domain.skill.constants import MAX_SKILL_SLOTS
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_proposal import (
    SkillProposal,
    SkillProposalContext,
    SkillProposalTable,
    SkillProposalTableEntry,
)


class SkillProposalDomainService:
    """重み付きでスキル提案を生成するドメインサービス。"""

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()
        self._proposal_sequence = 0

    def generate(
        self,
        context: SkillProposalContext,
        table: SkillProposalTable,
        max_proposals: int = 3,
    ) -> List[SkillProposal]:
        if max_proposals <= 0:
            return []

        eligible = [entry for entry in table.entries if self._is_eligible(entry, context)]
        if not eligible:
            return []

        # 重複提案を抑えるため、同一 offered_skill_id は1回だけ採択する。
        proposals: List[SkillProposal] = []
        used_skill_ids: set[SkillId] = set()
        pool = list(eligible)
        while pool and len(proposals) < max_proposals:
            chosen = self._weighted_choice(pool)
            if chosen.offered_skill_id in used_skill_ids:
                pool.remove(chosen)
                continue
            used_skill_ids.add(chosen.offered_skill_id)
            self._proposal_sequence += 1
            proposals.append(
                SkillProposal(
                    proposal_id=self._proposal_sequence,
                    proposal_type=chosen.proposal_type,
                    offered_skill_id=chosen.offered_skill_id,
                    deck_tier=chosen.deck_tier,
                    target_slot_index=self._pick_target_slot(context),
                    required_skill_ids=chosen.required_skill_ids,
                    reason=self._build_reason(chosen),
                )
            )
            pool.remove(chosen)
        return proposals

    def _is_eligible(self, entry: SkillProposalTableEntry, context: SkillProposalContext) -> bool:
        if context.player_level < entry.min_player_level:
            return False
        if entry.max_player_level is not None and context.player_level > entry.max_player_level:
            return False
        if entry.required_race is not None and context.player_race != entry.required_race:
            return False
        if entry.required_element is not None and context.player_element != entry.required_element:
            return False
        if entry.required_role is not None and context.player_role != entry.required_role:
            return False
        if context.free_capacity_ratio < entry.min_free_capacity_ratio:
            return False
        if context.free_capacity_ratio > entry.max_free_capacity_ratio:
            return False
        if any(req not in context.current_skill_ids for req in entry.required_skill_ids):
            return False
        return True

    def _weighted_choice(self, entries: List[SkillProposalTableEntry]) -> SkillProposalTableEntry:
        total_weight = sum(entry.weight for entry in entries)
        pick = self._rng.uniform(0, total_weight)
        acc = 0.0
        for entry in entries:
            acc += entry.weight
            if pick <= acc:
                return entry
        return entries[-1]

    def _pick_target_slot(self, context: SkillProposalContext) -> int:
        empty_slots = context.empty_slot_indices
        if empty_slots:
            return empty_slots[0]
        return self._rng.randint(0, MAX_SKILL_SLOTS - 1)

    @staticmethod
    def _build_reason(entry: SkillProposalTableEntry) -> str:
        parts: list[str] = [f"提案種別: {entry.proposal_type.value}"]
        parts.append(f"推奨レベル帯: {entry.min_player_level}~{entry.max_player_level or '上限なし'}")
        parts.append(
            f"空き容量条件: {entry.min_free_capacity_ratio:.2f}~{entry.max_free_capacity_ratio:.2f}"
        )
        if entry.required_race is not None:
            parts.append(f"種族条件: {entry.required_race.value}")
        if entry.required_element is not None:
            parts.append(f"属性条件: {entry.required_element.value}")
        if entry.required_role is not None:
            parts.append(f"ロール条件: {entry.required_role.value}")
        if entry.required_skill_ids:
            required = ",".join(str(skill_id.value) for skill_id in entry.required_skill_ids)
            parts.append(f"前提スキル: {required}")
        return " / ".join(parts)


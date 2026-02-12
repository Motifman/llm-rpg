import random
import pytest
from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.skill.enum.skill_enum import SkillProposalType
from ai_rpg_world.domain.skill.service.skill_proposal_domain_service import SkillProposalDomainService
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_proposal import (
    SkillProposalContext,
    SkillProposalTable,
    SkillProposalTableEntry,
)


class TestSkillProposalDomainService:
    class TestGenerate:
        def test_generate_respects_context_filters(self):
            service = SkillProposalDomainService(rng=random.Random(0))
            context = SkillProposalContext(
                player_level=12,
                player_race=Race.HUMAN,
                player_element=Element.FIRE,
                player_role=Role.ADVENTURER,
                free_capacity_ratio=0.8,
                current_skill_ids=(SkillId(1), SkillId(2)),
                current_slots=(SkillId(1), None, SkillId(2), None, None),
            )
            table = SkillProposalTable(
                table_id=1,
                entries=(
                    SkillProposalTableEntry(
                        proposal_type=SkillProposalType.ADD,
                        offered_skill_id=SkillId(10),
                        weight=2,
                        required_element=Element.FIRE,
                        min_player_level=10,
                        max_player_level=20,
                    ),
                    SkillProposalTableEntry(
                        proposal_type=SkillProposalType.REPLACE,
                        offered_skill_id=SkillId(20),
                        weight=5,
                        required_element=Element.WATER,
                    ),
                ),
            )

            proposals = service.generate(context=context, table=table, max_proposals=3)

            assert len(proposals) == 1
            assert proposals[0].offered_skill_id == SkillId(10)
            assert proposals[0].target_slot_index == 1
            assert "提案種別" in proposals[0].reason

        def test_generate_uses_required_skill_ids(self):
            service = SkillProposalDomainService(rng=random.Random(1))
            context = SkillProposalContext(
                player_level=30,
                player_race=Race.HUMAN,
                player_element=Element.NEUTRAL,
                player_role=Role.ADVENTURER,
                free_capacity_ratio=0.2,
                current_skill_ids=(SkillId(1), SkillId(2)),
                current_slots=(SkillId(1), SkillId(2), SkillId(4), SkillId(5), SkillId(6)),
            )
            table = SkillProposalTable(
                table_id=2,
                entries=(
                    SkillProposalTableEntry(
                        proposal_type=SkillProposalType.FUSE,
                        offered_skill_id=SkillId(99),
                        weight=1,
                        required_skill_ids=(SkillId(1), SkillId(2)),
                    ),
                    SkillProposalTableEntry(
                        proposal_type=SkillProposalType.FUSE,
                        offered_skill_id=SkillId(100),
                        weight=1,
                        required_skill_ids=(SkillId(1), SkillId(3)),
                    ),
                ),
            )
            proposals = service.generate(context=context, table=table, max_proposals=2)
            assert any(p.offered_skill_id == SkillId(99) for p in proposals)
            assert all(p.offered_skill_id != SkillId(100) for p in proposals)
            assert all(0 <= p.target_slot_index <= 4 for p in proposals)

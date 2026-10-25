import random
from dataclasses import replace

import pytest

from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.service.skill_proposal_domain_service import SkillProposalDomainService
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_proposal import (
    SkillProposalContext,
    SkillProposalTable,
    SkillProposalTableEntry,
)


class TestSkillProposalDomainService:
    class TestGenerate:
        @pytest.mark.parametrize(
            "context_changes,entry_changes,expected_ids,legacy_single",
            [
                pytest.param({}, {}, [10], False, id="original-context"),
                pytest.param({"player_level": 9}, {}, [], False, id="below-min-level"),
                pytest.param({"player_level": 10}, {}, [10], False, id="at-min-level"),
                pytest.param({"player_level": 20}, {}, [10], False, id="at-max-level"),
                pytest.param({"player_level": 21}, {}, [], False, id="above-max-level"),
                pytest.param({}, {"required_race": Race.HUMAN}, [10], False, id="matching-race"),
                pytest.param(
                    {"player_race": Race.GHOST},
                    {"required_race": Race.HUMAN},
                    [],
                    False,
                    id="wrong-race",
                ),
                pytest.param({}, {"required_role": Role.ADVENTURER}, [10], False, id="matching-role"),
                pytest.param(
                    {"player_role": Role.MERCHANT},
                    {"required_role": Role.ADVENTURER},
                    [],
                    False,
                    id="wrong-role",
                ),
                pytest.param(
                    {"free_capacity_ratio": 0.19},
                    {"min_free_capacity_ratio": 0.2, "max_free_capacity_ratio": 0.8},
                    [],
                    False,
                    id="below-min-capacity",
                ),
                pytest.param(
                    {"free_capacity_ratio": 0.2},
                    {"min_free_capacity_ratio": 0.2, "max_free_capacity_ratio": 0.8},
                    [10],
                    False,
                    id="at-min-capacity",
                ),
                pytest.param(
                    {"free_capacity_ratio": 0.8},
                    {"min_free_capacity_ratio": 0.2, "max_free_capacity_ratio": 0.8},
                    [10],
                    False,
                    id="at-max-capacity",
                ),
                pytest.param(
                    {"free_capacity_ratio": 0.81},
                    {"min_free_capacity_ratio": 0.2, "max_free_capacity_ratio": 0.8},
                    [],
                    False,
                    id="above-max-capacity",
                ),
                pytest.param({}, {}, [99], True, id="moved-registration-input"),
            ],
        )
        def test_generate_respects_context_filters(self, context_changes, entry_changes, expected_ids, legacy_single):
            """条件を満たす候補だけを返し、レベル・空き容量の両端を含め、最初の空枠を示す。"""
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
            allowed_entry = SkillProposalTableEntry(
                proposal_type=SkillProposalType.ADD,
                offered_skill_id=SkillId(10),
                weight=2,
                required_element=Element.FIRE,
                min_player_level=10,
                max_player_level=20,
            )
            entries = (
                replace(allowed_entry, **entry_changes),
                SkillProposalTableEntry(
                    proposal_type=SkillProposalType.REPLACE,
                    offered_skill_id=SkillId(20),
                    weight=5,
                    required_element=Element.WATER,
                ),
            )
            context = replace(context, **context_changes)
            max_proposals = 3
            if legacy_single:
                # 集約試験が準備に使っていた生成入力を、生成の所有者へそのまま移す。
                context = SkillProposalContext(
                    player_level=10,
                    player_race=Race.HUMAN,
                    player_element=Element.NEUTRAL,
                    player_role=Role.ADVENTURER,
                    free_capacity_ratio=0.5,
                    current_skill_ids=(SkillId(1),),
                    current_slots=(SkillId(1), None, None, None, None),
                )
                entries = (
                    SkillProposalTableEntry(
                        proposal_type=SkillProposalType.ADD,
                        offered_skill_id=SkillId(99),
                        weight=1,
                    ),
                )
                max_proposals = 1

            proposals = service.generate(
                context=context,
                table=SkillProposalTable(table_id=1, entries=entries),
                max_proposals=max_proposals,
            )

            assert [proposal.offered_skill_id.value for proposal in proposals] == expected_ids
            for proposal in proposals:
                assert proposal.proposal_type == SkillProposalType.ADD
                assert proposal.deck_tier == DeckTier.NORMAL
                assert proposal.target_slot_index == 1
                assert "提案種別" in proposal.reason
                assert "add" in proposal.reason

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

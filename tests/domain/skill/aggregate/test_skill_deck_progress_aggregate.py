import pytest
from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.skill.service.skill_proposal_domain_service import SkillProposalDomainService
from ai_rpg_world.domain.skill.enum.skill_enum import SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_deck_exp_table import SkillDeckExpTable
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_proposal import (
    SkillProposalContext,
    SkillProposalTable,
    SkillProposalTableEntry,
)
from ai_rpg_world.domain.skill.event.skill_events import SkillDeckLeveledUpEvent, SkillDeckExpGainedEvent


class TestSkillDeckProgressAggregate:
    class TestGrantExp:
        def test_grant_exp_levels_up_and_capacity_bonus_increases(self):
            exp_table = SkillDeckExpTable(base_exp=10, exponent=1.0, level_offset=0)
            agg = SkillDeckProgressAggregate(
                progress_id=SkillDeckProgressId(1),
                owner_id=100,
                exp_table=exp_table,
                capacity_growth_per_level=2,
            )
            agg.grant_exp(25)

            assert agg.deck_level == 3
            assert agg.capacity_bonus() == 4
            
            # イベント検証
            events = agg.get_events()
            assert any(isinstance(e, SkillDeckExpGainedEvent) for e in events)
            assert any(isinstance(e, SkillDeckLeveledUpEvent) for e in events)

        def test_grant_exp_multiple_level_ups(self):
            exp_table = SkillDeckExpTable(base_exp=10, exponent=1.0, level_offset=0)
            agg = SkillDeckProgressAggregate(
                progress_id=SkillDeckProgressId(1),
                owner_id=100,
                exp_table=exp_table,
                capacity_growth_per_level=1,
            )
            # base=10, offset=0, exponent=1.0:
            # L2: 10, L3: 20, L4: 30, L5: 40, L6: 50, L7: 60, L8: 70
            agg.grant_exp(65)
            
            assert agg.deck_level == 7
            assert agg.deck_exp == 65
            
            events = agg.get_events()
            level_up_events = [e for e in events if isinstance(e, SkillDeckLeveledUpEvent)]
            assert len(level_up_events) == 6
            assert level_up_events[0].new_level == 2
            assert level_up_events[-1].new_level == 7

    class TestCapacityBonus:
        def test_capacity_bonus_uses_level_table_when_provided(self):
            exp_table = SkillDeckExpTable(base_exp=10, exponent=1.0, level_offset=0)
            agg = SkillDeckProgressAggregate(
                progress_id=SkillDeckProgressId(10),
                owner_id=100,
                exp_table=exp_table,
                capacity_growth_per_level=99,
                capacity_bonus_by_level={1: 0, 2: 1, 3: 3, 5: 6},
            )
            agg.grant_exp(31)
            assert agg.deck_level == 4
            assert agg.capacity_bonus() == 3

    class TestProposalManagement:
        def test_register_and_accept_proposal(self):
            agg = SkillDeckProgressAggregate(progress_id=SkillDeckProgressId(2), owner_id=100)
            proposal = SkillProposalDomainService().generate(
                context=SkillProposalContext(
                    player_level=10,
                    player_race=Race.HUMAN,
                    player_element=Element.NEUTRAL,
                    player_role=Role.ADVENTURER,
                    free_capacity_ratio=0.5,
                    current_skill_ids=(SkillId(1),),
                    current_slots=(SkillId(1), None, None, None, None),
                ),
                table=SkillProposalTable(
                    table_id=1,
                    entries=(
                        SkillProposalTableEntry(
                            proposal_type=SkillProposalType.ADD,
                            offered_skill_id=SkillId(99),
                            weight=1,
                        ),
                    ),
                ),
                max_proposals=1,
            )[0]

            agg.register_proposals([proposal])
            accepted = agg.accept_proposal(proposal.proposal_id)

            assert accepted.offered_skill_id == SkillId(99)
            assert agg.pending_proposals == []

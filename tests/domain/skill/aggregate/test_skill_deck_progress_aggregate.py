from collections import Counter

import pytest

from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.event.skill_events import (
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEvolutionAcceptedEvent,
    SkillProposalGeneratedEvent,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_exp_table import SkillDeckExpTable
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_proposal import SkillProposal


class TestSkillDeckProgressAggregate:
    class TestGrantExp:
        @pytest.mark.parametrize(
            "initial_exp,amount,growth,total,level,bonus,level_steps",
            [
                pytest.param(0, 25, 2, 25, 3, 4, [(1, 2), (2, 3)], id="original-25"),
                pytest.param(
                    0,
                    65,
                    1,
                    65,
                    7,
                    6,
                    [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)],
                    id="original-65",
                ),
                pytest.param(0, 9, 1, 9, 1, 0, [], id="below-level-two"),
                pytest.param(0, 10, 1, 10, 2, 1, [(1, 2)], id="at-level-two"),
                pytest.param(5, 20, 2, 25, 3, 4, [(1, 2), (2, 3)], id="accumulates"),
            ],
        )
        def test_grant_exp_levels_up_and_capacity_bonus_increases(
            self, initial_exp, amount, growth, total, level, bonus, level_steps
        ):
            """経験値を累積して段階別の容量へ進め、獲得量と各昇格を一度ずつ通知する。"""
            agg = SkillDeckProgressAggregate(
                progress_id=SkillDeckProgressId(1),
                owner_id=100,
                deck_exp=initial_exp,
                exp_table=SkillDeckExpTable(base_exp=10, exponent=1.0, level_offset=0),
                capacity_growth_per_level=growth,
            )

            agg.grant_exp(amount)

            assert agg.deck_level == level
            assert agg.deck_exp == total
            assert agg.capacity_bonus() == bonus
            events = agg.get_events()
            gained = [event for event in events if isinstance(event, SkillDeckExpGainedEvent)]
            assert [(event.aggregate_id, event.gained_exp, event.total_exp) for event in gained] == [
                (SkillDeckProgressId(1), amount, total)
            ]
            leveled = [event for event in events if isinstance(event, SkillDeckLeveledUpEvent)]
            assert [(event.aggregate_id, event.old_level, event.new_level) for event in leveled] == [
                (SkillDeckProgressId(1), old, new) for old, new in level_steps
            ]

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
        @pytest.mark.parametrize("with_other_proposals", [False, True], ids=["original-single", "keep-others"])
        def test_register_and_accept_proposal(self, with_other_proposals):
            """指定した提案だけを受諾し、他の保留提案を残して登録・受諾の対象を通知する。"""
            agg = SkillDeckProgressAggregate(progress_id=SkillDeckProgressId(2), owner_id=100)
            proposal = SkillProposal(
                1,
                SkillProposalType.ADD,
                SkillId(99),
                target_slot_index=1,
                reason="提案種別: add / 推奨レベル帯: 1~上限なし / 空き容量条件: 0.00~1.00",
            )
            before = SkillProposal(
                2,
                SkillProposalType.FUSE,
                SkillId(101),
                deck_tier=DeckTier.AWAKENED,
                target_slot_index=4,
                required_skill_ids=(SkillId(1),),
            )
            after = SkillProposal(3, SkillProposalType.REPLACE, SkillId(102), target_slot_index=2)
            proposals = [before, proposal, after] if with_other_proposals else [proposal]

            expected_proposals = tuple(proposals)
            expected_generated = Counter(
                (SkillDeckProgressId(2), item.proposal_id, item.proposal_type, item.offered_skill_id)
                for item in expected_proposals
            )

            agg.register_proposals(proposals)

            assert tuple(agg.pending_proposals) == expected_proposals
            generated = agg.get_events()
            assert all(isinstance(event, SkillProposalGeneratedEvent) for event in generated)
            assert (
                Counter(
                    (event.aggregate_id, event.proposal_id, event.proposal_type, event.offered_skill_id)
                    for event in generated
                )
                == expected_generated
            )
            agg.clear_events()

            accepted = agg.accept_proposal(proposal.proposal_id)

            assert accepted == proposal
            assert agg.pending_proposals == ([before, after] if with_other_proposals else [])
            events = agg.get_events()
            assert len(events) == 1
            assert isinstance(events[0], SkillEvolutionAcceptedEvent)
            assert (
                events[0].aggregate_id,
                events[0].proposal_id,
                events[0].proposal_type,
                events[0].offered_skill_id,
            ) == (SkillDeckProgressId(2), 1, SkillProposalType.ADD, SkillId(99))

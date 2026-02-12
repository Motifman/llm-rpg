from typing import List, Optional

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.skill.event.skill_events import (
    SkillDeckExpGainedEvent,
    SkillDeckLeveledUpEvent,
    SkillEvolutionAcceptedEvent,
    SkillEvolutionRejectedEvent,
    SkillProposalGeneratedEvent,
)
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillProposalNotFoundException
from ai_rpg_world.domain.skill.value_object.skill_deck_exp_table import SkillDeckExpTable
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_proposal import (
    SkillProposal,
    SkillProposalContext,
    SkillProposalTable,
)


class SkillDeckProgressAggregate(AggregateRoot):
    """スキルデッキの経験値成長と進化提案を管理する集約。"""

    def __init__(
        self,
        progress_id: SkillDeckProgressId,
        owner_id: int,
        deck_level: int = 1,
        deck_exp: int = 0,
        exp_table: SkillDeckExpTable = SkillDeckExpTable(),
        capacity_growth_per_level: int = 1,
        capacity_bonus_by_level: Optional[dict[int, int]] = None,
        pending_proposals: Optional[List[SkillProposal]] = None,
    ):
        super().__init__()
        self._progress_id = progress_id
        self._owner_id = owner_id
        self._deck_level = max(1, deck_level)
        self._deck_exp = max(0, deck_exp)
        self._exp_table = exp_table
        self._capacity_growth_per_level = max(0, capacity_growth_per_level)
        self._capacity_bonus_by_level = dict(capacity_bonus_by_level or {})
        self._pending_proposals = list(pending_proposals or [])

    @property
    def progress_id(self) -> SkillDeckProgressId:
        return self._progress_id

    @property
    def owner_id(self) -> int:
        return self._owner_id

    @property
    def deck_level(self) -> int:
        return self._deck_level

    @property
    def deck_exp(self) -> int:
        return self._deck_exp

    @property
    def pending_proposals(self) -> List[SkillProposal]:
        return list(self._pending_proposals)

    def capacity_bonus(self) -> int:
        if self._capacity_bonus_by_level:
            applicable_levels = [level for level in self._capacity_bonus_by_level if level <= self._deck_level]
            if applicable_levels:
                best_level = max(applicable_levels)
                return max(0, self._capacity_bonus_by_level[best_level])
        return max(0, (self._deck_level - 1) * self._capacity_growth_per_level)

    def grant_exp(self, amount: int) -> None:
        if amount <= 0:
            return

        self._deck_exp += amount
        self.add_event(
            SkillDeckExpGainedEvent.create(
                aggregate_id=self._progress_id,
                aggregate_type="SkillDeckProgressAggregate",
                gained_exp=amount,
                total_exp=self._deck_exp,
                deck_level=self._deck_level,
            )
        )

        while True:
            next_level = self._deck_level + 1
            required = self._exp_table.get_required_exp_for_level(next_level)
            if self._deck_exp < required:
                break
            old_level = self._deck_level
            self._deck_level = next_level
            self.add_event(
                SkillDeckLeveledUpEvent.create(
                    aggregate_id=self._progress_id,
                    aggregate_type="SkillDeckProgressAggregate",
                    old_level=old_level,
                    new_level=self._deck_level,
                )
            )

    def register_proposals(self, proposals: List[SkillProposal]) -> None:
        self._pending_proposals = list(proposals)
        for proposal in proposals:
            self.add_event(
                SkillProposalGeneratedEvent.create(
                    aggregate_id=self._progress_id,
                    aggregate_type="SkillDeckProgressAggregate",
                    proposal_id=proposal.proposal_id,
                    proposal_type=proposal.proposal_type,
                    offered_skill_id=proposal.offered_skill_id,
                )
            )

    def accept_proposal(self, proposal_id: int) -> SkillProposal:
        found = None
        for proposal in self._pending_proposals:
            if proposal.proposal_id == proposal_id:
                found = proposal
                break
        if found is None:
            raise SkillProposalNotFoundException(f"proposal not found: {proposal_id}")

        self._pending_proposals = [
            proposal for proposal in self._pending_proposals if proposal.proposal_id != proposal_id
        ]
        self.add_event(
            SkillEvolutionAcceptedEvent.create(
                aggregate_id=self._progress_id,
                aggregate_type="SkillDeckProgressAggregate",
                proposal_id=found.proposal_id,
                proposal_type=found.proposal_type,
                offered_skill_id=found.offered_skill_id,
            )
        )
        return found

    def reject_proposal(self, proposal_id: int) -> None:
        found = None
        for proposal in self._pending_proposals:
            if proposal.proposal_id == proposal_id:
                found = proposal
                break
        if found is None:
            raise SkillProposalNotFoundException(f"proposal not found: {proposal_id}")

        self._pending_proposals = [
            proposal for proposal in self._pending_proposals if proposal.proposal_id != proposal_id
        ]
        self.add_event(
            SkillEvolutionRejectedEvent.create(
                aggregate_id=self._progress_id,
                aggregate_type="SkillDeckProgressAggregate",
                proposal_id=found.proposal_id,
                proposal_type=found.proposal_type,
                offered_skill_id=found.offered_skill_id,
            )
        )

    def refresh_proposals(
        self,
        context: SkillProposalContext,
        table: SkillProposalTable,
        proposal_service: "SkillProposalDomainService",
        max_proposals: int = 3,
    ) -> List[SkillProposal]:
        proposals = proposal_service.generate(context=context, table=table, max_proposals=max_proposals)
        self.register_proposals(proposals)
        return proposals


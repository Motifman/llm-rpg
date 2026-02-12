from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillProposalValidationException
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId


@dataclass(frozen=True)
class SkillProposal:
    proposal_id: int
    proposal_type: SkillProposalType
    offered_skill_id: SkillId
    deck_tier: DeckTier = DeckTier.NORMAL
    target_slot_index: Optional[int] = None
    required_skill_ids: Tuple[SkillId, ...] = ()
    reason: str = ""

    def __post_init__(self):
        if self.proposal_id <= 0:
            raise SkillProposalValidationException(
                f"proposal_id must be positive: {self.proposal_id}"
            )
        if self.target_slot_index is not None and (self.target_slot_index < 0 or self.target_slot_index >= 5):
            raise SkillProposalValidationException(
                f"target_slot_index must be in range 0..4: {self.target_slot_index}"
            )


@dataclass(frozen=True)
class SkillProposalContext:
    player_level: int
    player_race: Race
    player_element: Element
    player_role: Role
    free_capacity_ratio: float
    current_skill_ids: Tuple[SkillId, ...]
    current_slots: Tuple[Optional[SkillId], ...] = ()

    def __post_init__(self):
        if self.player_level <= 0:
            raise SkillProposalValidationException(
                f"player_level must be positive: {self.player_level}"
            )
        if self.free_capacity_ratio < 0 or self.free_capacity_ratio > 1:
            raise SkillProposalValidationException(
                f"free_capacity_ratio must be in [0, 1]: {self.free_capacity_ratio}"
            )
        if self.current_slots and len(self.current_slots) != 5:
            raise SkillProposalValidationException(
                f"current_slots length must be 5 when provided: {len(self.current_slots)}"
            )

    @property
    def empty_slot_indices(self) -> Tuple[int, ...]:
        if not self.current_slots:
            return ()
        return tuple(idx for idx, skill_id in enumerate(self.current_slots) if skill_id is None)


@dataclass(frozen=True)
class SkillProposalTableEntry:
    proposal_type: SkillProposalType
    offered_skill_id: SkillId
    deck_tier: DeckTier = DeckTier.NORMAL
    weight: int = 1
    min_player_level: int = 1
    max_player_level: Optional[int] = None
    required_race: Optional[Race] = None
    required_element: Optional[Element] = None
    required_role: Optional[Role] = None
    min_free_capacity_ratio: float = 0.0
    max_free_capacity_ratio: float = 1.0
    required_skill_ids: Tuple[SkillId, ...] = ()

    def __post_init__(self):
        if self.weight <= 0:
            raise SkillProposalValidationException(f"weight must be positive: {self.weight}")
        if self.min_player_level <= 0:
            raise SkillProposalValidationException(
                f"min_player_level must be positive: {self.min_player_level}"
            )
        if self.max_player_level is not None and self.max_player_level < self.min_player_level:
            raise SkillProposalValidationException(
                "max_player_level must be greater than or equal to min_player_level"
            )
        if self.min_free_capacity_ratio < 0 or self.min_free_capacity_ratio > 1:
            raise SkillProposalValidationException(
                "min_free_capacity_ratio must be in [0, 1]"
            )
        if self.max_free_capacity_ratio < 0 or self.max_free_capacity_ratio > 1:
            raise SkillProposalValidationException(
                "max_free_capacity_ratio must be in [0, 1]"
            )
        if self.min_free_capacity_ratio > self.max_free_capacity_ratio:
            raise SkillProposalValidationException(
                "min_free_capacity_ratio must be <= max_free_capacity_ratio"
            )


@dataclass(frozen=True)
class SkillProposalTable:
    table_id: int
    entries: Tuple[SkillProposalTableEntry, ...]

    def __post_init__(self):
        if self.table_id <= 0:
            raise SkillProposalValidationException(f"table_id must be positive: {self.table_id}")
        if not self.entries:
            raise SkillProposalValidationException("entries cannot be empty")


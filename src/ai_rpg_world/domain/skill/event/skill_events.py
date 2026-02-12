from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId


@dataclass(frozen=True)
class SkillEquippedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    deck_tier: DeckTier
    slot_index: int
    skill_id: SkillId


@dataclass(frozen=True)
class SkillUnequippedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    deck_tier: DeckTier
    slot_index: int
    removed_skill_id: SkillId


@dataclass(frozen=True)
class SkillUsedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    skill_id: SkillId
    deck_tier: DeckTier
    cast_lock_until_tick: int
    cooldown_until_tick: int


@dataclass(frozen=True)
class SkillCooldownStartedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    skill_id: SkillId
    cooldown_until_tick: int


@dataclass(frozen=True)
class AwakenedModeActivatedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    activated_at_tick: int
    expires_at_tick: int


@dataclass(frozen=True)
class AwakenedModeExpiredEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    expired_at_tick: int


@dataclass(frozen=True)
class SkillLoadoutCapacityChangedEvent(BaseDomainEvent[SkillLoadoutId, "SkillLoadoutAggregate"]):
    normal_capacity: int
    awakened_capacity: int


@dataclass(frozen=True)
class SkillDeckExpGainedEvent(BaseDomainEvent[SkillDeckProgressId, "SkillDeckProgressAggregate"]):
    gained_exp: int
    total_exp: int
    deck_level: int


@dataclass(frozen=True)
class SkillDeckLeveledUpEvent(BaseDomainEvent[SkillDeckProgressId, "SkillDeckProgressAggregate"]):
    old_level: int
    new_level: int


@dataclass(frozen=True)
class SkillProposalGeneratedEvent(BaseDomainEvent[SkillDeckProgressId, "SkillDeckProgressAggregate"]):
    proposal_id: int
    proposal_type: SkillProposalType
    offered_skill_id: SkillId


@dataclass(frozen=True)
class SkillEvolutionAcceptedEvent(BaseDomainEvent[SkillDeckProgressId, "SkillDeckProgressAggregate"]):
    proposal_id: int
    proposal_type: SkillProposalType
    offered_skill_id: SkillId


@dataclass(frozen=True)
class SkillEvolutionRejectedEvent(BaseDomainEvent[SkillDeckProgressId, "SkillDeckProgressAggregate"]):
    proposal_id: int
    proposal_type: SkillProposalType
    offered_skill_id: SkillId


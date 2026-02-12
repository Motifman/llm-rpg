from dataclasses import dataclass

from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


@dataclass(frozen=True)
class EquipPlayerSkillCommand:
    player_id: int
    loadout_id: int
    deck_tier: DeckTier
    slot_index: int
    skill_id: int


@dataclass(frozen=True)
class ActivatePlayerAwakenedModeCommand:
    player_id: int
    loadout_id: int
    current_tick: int
    duration_ticks: int
    cooldown_reduction_rate: float
    mp_cost: int = 0
    stamina_cost: int = 0
    hp_cost: int = 0


@dataclass(frozen=True)
class GrantSkillDeckExpCommand:
    progress_id: int
    exp_amount: int


@dataclass(frozen=True)
class AcceptSkillProposalCommand:
    progress_id: int
    proposal_id: int


@dataclass(frozen=True)
class RejectSkillProposalCommand:
    progress_id: int
    proposal_id: int


@dataclass(frozen=True)
class UsePlayerSkillCommand:
    player_id: int
    loadout_id: int
    slot_index: int
    current_tick: int


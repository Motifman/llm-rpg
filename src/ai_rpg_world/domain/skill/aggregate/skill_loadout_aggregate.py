from dataclasses import dataclass
from math import floor
from typing import Dict

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.event.skill_events import (
    AwakenedModeActivatedEvent,
    AwakenedModeExpiredEvent,
    SkillCooldownStartedEvent,
    SkillEquippedEvent,
    SkillLoadoutCapacityChangedEvent,
    SkillUnequippedEvent,
    SkillUsedEvent,
)
from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillAwakenStateException,
    SkillCastLockActiveException,
    SkillCooldownActiveException,
    SkillNotFoundInSlotException,
    SkillOwnerMismatchException,
    SkillPrerequisiteNotMetException,
)
from ai_rpg_world.domain.skill.value_object.skill_deck import SkillDeck
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


@dataclass(frozen=True)
class AwakenState:
    is_active: bool = False
    active_until_tick: int = 0
    cooldown_reduction_rate: float = 0.0

    def __post_init__(self):
        if self.active_until_tick < 0:
            raise SkillAwakenStateException(
                f"active_until_tick cannot be negative: {self.active_until_tick}"
            )
        if self.cooldown_reduction_rate < 0 or self.cooldown_reduction_rate >= 1:
            raise SkillAwakenStateException(
                f"cooldown_reduction_rate must be in [0, 1): {self.cooldown_reduction_rate}"
            )


class SkillLoadoutAggregate(AggregateRoot):
    """通常/上位デッキとクールタイムを管理する集約。"""

    def __init__(
        self,
        loadout_id: SkillLoadoutId,
        owner_id: int,
        normal_deck: SkillDeck,
        awakened_deck: SkillDeck,
        awaken_state: AwakenState = AwakenState(),
        skill_cooldowns_until: Dict[int, int] | None = None,
        cast_lock_until_tick: int = 0,
    ):
        super().__init__()
        self._loadout_id = loadout_id
        self._owner_id = owner_id
        self._normal_deck = normal_deck
        self._awakened_deck = awakened_deck
        self._awaken_state = awaken_state
        self._skill_cooldowns_until = dict(skill_cooldowns_until or {})
        self._cast_lock_until_tick = cast_lock_until_tick

    @classmethod
    def create(
        cls,
        loadout_id: SkillLoadoutId,
        owner_id: int,
        normal_capacity: int,
        awakened_capacity: int,
    ) -> "SkillLoadoutAggregate":
        return cls(
            loadout_id=loadout_id,
            owner_id=owner_id,
            normal_deck=SkillDeck(capacity=normal_capacity, deck_tier=DeckTier.NORMAL),
            awakened_deck=SkillDeck(capacity=awakened_capacity, deck_tier=DeckTier.AWAKENED),
        )

    @property
    def loadout_id(self) -> SkillLoadoutId:
        return self._loadout_id

    @property
    def owner_id(self) -> int:
        return self._owner_id

    @property
    def normal_deck(self) -> SkillDeck:
        return self._normal_deck

    @property
    def awakened_deck(self) -> SkillDeck:
        return self._awakened_deck

    @property
    def awaken_state(self) -> AwakenState:
        return self._awaken_state

    @property
    def cast_lock_until_tick(self) -> int:
        return self._cast_lock_until_tick

    def current_deck_tier(self, current_tick: int) -> DeckTier:
        if self._awaken_state.is_active and current_tick < self._awaken_state.active_until_tick:
            return DeckTier.AWAKENED
        return DeckTier.NORMAL

    def tick(self, current_tick: int) -> None:
        if self._awaken_state.is_active and current_tick >= self._awaken_state.active_until_tick:
            self._awaken_state = AwakenState(
                is_active=False,
                active_until_tick=self._awaken_state.active_until_tick,
                cooldown_reduction_rate=self._awaken_state.cooldown_reduction_rate,
            )
            self.add_event(
                AwakenedModeExpiredEvent.create(
                    aggregate_id=self._loadout_id,
                    aggregate_type="SkillLoadoutAggregate",
                    expired_at_tick=current_tick,
                )
            )

    def update_capacity(self, normal_capacity: int, awakened_capacity: int) -> None:
        """デッキの最大キャパシティを更新する。"""
        self._normal_deck = SkillDeck(
            capacity=normal_capacity,
            deck_tier=self._normal_deck.deck_tier,
            slots=self._normal_deck.slots,
        )
        self._awakened_deck = SkillDeck(
            capacity=awakened_capacity,
            deck_tier=self._awakened_deck.deck_tier,
            slots=self._awakened_deck.slots,
        )
        self.add_event(
            SkillLoadoutCapacityChangedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                normal_capacity=normal_capacity,
                awakened_capacity=awakened_capacity,
            )
        )

    def equip_skill(self, deck_tier: DeckTier, slot_index: int, skill: SkillSpec, actor_id: int | None = None) -> None:
        if actor_id is not None and actor_id != self._owner_id:
            raise SkillOwnerMismatchException(
                f"actor_id mismatch: expected={self._owner_id}, actual={actor_id}"
            )
        self._validate_skill_prerequisites(deck_tier=deck_tier, slot_index=slot_index, skill=skill)
        if deck_tier == DeckTier.NORMAL:
            self._normal_deck = self._normal_deck.equip(slot_index, skill)
        else:
            self._awakened_deck = self._awakened_deck.equip(slot_index, skill)
        self.add_event(
            SkillEquippedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                deck_tier=deck_tier,
                slot_index=slot_index,
                skill_id=skill.skill_id,
            )
        )

    def unequip_skill(self, deck_tier: DeckTier, slot_index: int, actor_id: int | None = None) -> None:
        if actor_id is not None and actor_id != self._owner_id:
            raise SkillOwnerMismatchException(
                f"actor_id mismatch: expected={self._owner_id}, actual={actor_id}"
            )
        target_deck = self._normal_deck if deck_tier == DeckTier.NORMAL else self._awakened_deck
        old_skill = target_deck.get_skill(slot_index)
        if old_skill is None:
            raise SkillNotFoundInSlotException(
                f"slot has no skill: tier={deck_tier.value}, slot={slot_index}"
            )
        next_deck = target_deck.unequip(slot_index)
        if deck_tier == DeckTier.NORMAL:
            self._normal_deck = next_deck
        else:
            self._awakened_deck = next_deck
        self.add_event(
            SkillUnequippedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                deck_tier=deck_tier,
                slot_index=slot_index,
                removed_skill_id=old_skill.skill_id,
            )
        )

    def activate_awakened_mode(
        self,
        current_tick: int,
        duration_ticks: int,
        cooldown_reduction_rate: float,
        actor_id: int | None = None,
    ) -> None:
        if actor_id is not None and actor_id != self._owner_id:
            raise SkillOwnerMismatchException(
                f"actor_id mismatch: expected={self._owner_id}, actual={actor_id}"
            )
        if duration_ticks <= 0:
            raise SkillAwakenStateException("duration_ticks must be greater than 0")
        if self._awaken_state.is_active and current_tick < self._awaken_state.active_until_tick:
            raise SkillAwakenStateException("awakened mode is already active")
        expires_at = current_tick + duration_ticks
        self._awaken_state = AwakenState(
            is_active=True,
            active_until_tick=expires_at,
            cooldown_reduction_rate=cooldown_reduction_rate,
        )
        self.add_event(
            AwakenedModeActivatedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                activated_at_tick=current_tick,
                expires_at_tick=expires_at,
            )
        )

    def can_use_skill(self, slot_index: int, current_tick: int) -> bool:
        if current_tick < self._cast_lock_until_tick:
            return False
        skill = self.get_current_deck(current_tick).get_skill(slot_index)
        if skill is None:
            return False
        return self._skill_cooldowns_until.get(skill.skill_id.value, 0) <= current_tick

    def use_skill(self, slot_index: int, current_tick: int, actor_id: int | None = None) -> SkillSpec:
        if actor_id is not None and actor_id != self._owner_id:
            raise SkillOwnerMismatchException(
                f"actor_id mismatch: expected={self._owner_id}, actual={actor_id}"
            )
        
        if current_tick < self._cast_lock_until_tick:
            raise SkillCastLockActiveException(
                f"actor is in cast lock until tick {self._cast_lock_until_tick}"
            )

        deck_tier = self.current_deck_tier(current_tick)
        skill = self.get_current_deck(current_tick).get_skill(slot_index)
        if skill is None:
            raise SkillNotFoundInSlotException(
                f"slot has no skill: tier={deck_tier.value}, slot={slot_index}"
            )

        cooldown_until = self._skill_cooldowns_until.get(skill.skill_id.value, 0)
        if cooldown_until > current_tick:
            raise SkillCooldownActiveException(
                f"skill {skill.skill_id.value} is on cooldown until tick {cooldown_until}"
            )

        self._cast_lock_until_tick = current_tick + skill.cast_lock_ticks
        adjusted_cooldown = skill.cooldown_ticks
        if deck_tier == DeckTier.AWAKENED:
            adjusted_cooldown = max(
                0,
                floor(skill.cooldown_ticks * (1 - self._awaken_state.cooldown_reduction_rate)),
            )
        next_ready_tick = current_tick + adjusted_cooldown
        self._skill_cooldowns_until[skill.skill_id.value] = next_ready_tick

        self.add_event(
            SkillCooldownStartedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                skill_id=skill.skill_id,
                cooldown_until_tick=next_ready_tick,
            )
        )
        self.add_event(
            SkillUsedEvent.create(
                aggregate_id=self._loadout_id,
                aggregate_type="SkillLoadoutAggregate",
                skill_id=skill.skill_id,
                deck_tier=deck_tier,
                cast_lock_until_tick=self._cast_lock_until_tick,
                cooldown_until_tick=next_ready_tick,
            )
        )
        return skill

    def get_current_deck(self, current_tick: int) -> SkillDeck:
        tier = self.current_deck_tier(current_tick)
        return self._awakened_deck if tier == DeckTier.AWAKENED else self._normal_deck

    def _validate_skill_prerequisites(self, deck_tier: DeckTier, slot_index: int, skill: SkillSpec) -> None:
        if not skill.required_skill_ids:
            return
        target_deck = self._normal_deck if deck_tier == DeckTier.NORMAL else self._awakened_deck
        equipped_ids = {
            equipped.skill_id.value
            for idx, equipped in enumerate(target_deck.slots)
            if equipped is not None and idx != slot_index
        }
        missing = [required for required in skill.required_skill_ids if required.value not in equipped_ids]
        if missing:
            raise SkillPrerequisiteNotMetException(
                f"missing required skills: {[required.value for required in missing]}"
            )


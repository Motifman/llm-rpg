from dataclasses import dataclass, field
from typing import Optional, Tuple

from ai_rpg_world.domain.skill.constants import MAX_SKILL_SLOTS
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillAlreadyEquippedException,
    SkillDeckCapacityExceededException,
    SkillDeckValidationException,
)
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec


@dataclass(frozen=True)
class SkillDeck:
    capacity: int
    deck_tier: DeckTier
    slots: Tuple[Optional[SkillSpec], ...] = field(
        default_factory=lambda: tuple(None for _ in range(MAX_SKILL_SLOTS))
    )

    def __post_init__(self):
        if self.capacity < 0:
            raise SkillDeckValidationException(f"capacity cannot be negative: {self.capacity}")
        if len(self.slots) != MAX_SKILL_SLOTS:
            raise SkillDeckValidationException(
                f"slots length must be {MAX_SKILL_SLOTS}: {len(self.slots)}"
            )

        for skill in self.slots:
            if skill and skill.is_awakened_deck_only and self.deck_tier != DeckTier.AWAKENED:
                raise SkillDeckValidationException("awakened-only skill cannot be equipped in normal deck")

        if self.total_cost > self.capacity:
            raise SkillDeckCapacityExceededException(
                f"deck total cost exceeds capacity: {self.total_cost} > {self.capacity}"
            )

    @property
    def total_cost(self) -> int:
        return sum(skill.deck_cost for skill in self.slots if skill is not None)

    @property
    def empty_slot_count(self) -> int:
        return sum(1 for s in self.slots if s is None)

    @property
    def free_capacity(self) -> int:
        return max(0, self.capacity - self.total_cost)

    def get_skill(self, slot_index: int) -> Optional[SkillSpec]:
        self._validate_slot_index(slot_index)
        return self.slots[slot_index]

    def equip(self, slot_index: int, skill: SkillSpec) -> "SkillDeck":
        self._validate_slot_index(slot_index)
        if skill.is_awakened_deck_only and self.deck_tier != DeckTier.AWAKENED:
            raise SkillDeckValidationException("awakened-only skill cannot be equipped in normal deck")

        # 同一スキルの重複装備チェック
        if self.contains_skill(skill.skill_id.value):
            # すでに装備されているスロットが現在のスロットでない場合のみエラー
            existing_skill = self.get_skill(slot_index)
            if existing_skill is None or existing_skill.skill_id != skill.skill_id:
                raise SkillAlreadyEquippedException(
                    f"skill {skill.skill_id.value} is already equipped in another slot"
                )

        next_slots = list(self.slots)
        next_slots[slot_index] = skill
        return SkillDeck(capacity=self.capacity, deck_tier=self.deck_tier, slots=tuple(next_slots))

    def unequip(self, slot_index: int) -> "SkillDeck":
        self._validate_slot_index(slot_index)
        next_slots = list(self.slots)
        next_slots[slot_index] = None
        return SkillDeck(capacity=self.capacity, deck_tier=self.deck_tier, slots=tuple(next_slots))

    def contains_skill(self, skill_id: int) -> bool:
        return any(skill is not None and skill.skill_id.value == skill_id for skill in self.slots)

    @staticmethod
    def _validate_slot_index(slot_index: int) -> None:
        if slot_index < 0 or slot_index >= MAX_SKILL_SLOTS:
            raise SkillDeckValidationException(
                f"slot_index must be in range 0..{MAX_SKILL_SLOTS - 1}: {slot_index}"
            )


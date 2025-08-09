from dataclasses import dataclass, field
from typing import Dict, Optional

from game.enums import AppearanceSlot
from game.item.item import AppearanceItem


@dataclass
class AppearanceSet:
    """見た目（服飾）を管理するクラス。
    装着は戦闘性能に影響しない。外見専用テキストを提供する。
    """
    slots: Dict[AppearanceSlot, Optional[AppearanceItem]] = field(default_factory=dict)
    base_description: str = ""  # 服飾に関わらない簡単な容姿の説明

    def set_base_description(self, description: str):
        self.base_description = description or ""

    def get_base_description(self) -> str:
        return self.base_description

    def get_equipped(self, slot: AppearanceSlot) -> Optional[AppearanceItem]:
        return self.slots.get(slot)

    def equip(self, slot: AppearanceSlot, item: AppearanceItem) -> Optional[AppearanceItem]:
        previous = self.slots.get(slot)
        self.slots[slot] = item
        return previous

    def unequip(self, slot: AppearanceSlot) -> Optional[AppearanceItem]:
        previous = self.slots.get(slot)
        if slot in self.slots:
            self.slots[slot] = None
        return previous

    def get_appearance_description(self) -> str:
        parts: list[str] = []
        base = self.base_description.strip()
        if base:
            parts.append(base)
        for slot in AppearanceSlot:
            item = self.slots.get(slot)
            if item:
                parts.append(f"{slot.value}: {item.appearance_text or item.name}")
        return "見た目: " + (", ".join(parts) if parts else "なし")



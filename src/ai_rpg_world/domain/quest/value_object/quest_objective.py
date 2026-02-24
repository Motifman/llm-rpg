from dataclasses import dataclass
from typing import List, Optional

from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType


@dataclass(frozen=True)
class QuestObjective:
    """クエスト目標の値オブジェクト

    target_id は種別に応じた ID（KILL_MONSTER の場合は MonsterTemplateId の値など）を int で保持。
    TAKE_FROM_CHEST の場合は target_id=spot_id.value, target_id_secondary=chest_id.value とする。
    """
    objective_type: QuestObjectiveType
    target_id: int
    required_count: int
    current_count: int = 0
    target_id_secondary: Optional[int] = None

    def __post_init__(self):
        if self.required_count <= 0:
            raise ValueError("required_count must be positive")
        if self.current_count < 0 or self.current_count > self.required_count:
            raise ValueError("current_count must be in [0, required_count]")

    def with_progress(self, delta: int = 1) -> "QuestObjective":
        """進捗を加算した新しい目標を返す（不変）"""
        new_count = min(self.current_count + delta, self.required_count)
        return QuestObjective(
            objective_type=self.objective_type,
            target_id=self.target_id,
            required_count=self.required_count,
            current_count=new_count,
            target_id_secondary=self.target_id_secondary,
        )

    def is_completed(self) -> bool:
        return self.current_count >= self.required_count

from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.quest.exception.quest_exception import QuestIdValidationException


@dataclass(frozen=True)
class QuestId:
    """クエストID値オブジェクト

    IDは正の整数である必要があります。既存の TradeId 等と同様の形式。
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise QuestIdValidationException(f"Quest ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "QuestId":
        """intまたはstrからQuestIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise QuestIdValidationException(value)
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QuestId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

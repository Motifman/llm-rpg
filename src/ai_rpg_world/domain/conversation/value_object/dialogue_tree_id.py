from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class DialogueTreeId:
    """ダイアログツリーID値オブジェクト"""

    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError(f"DialogueTreeId must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "DialogueTreeId":
        if isinstance(value, str):
            int_value = int(value)
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DialogueTreeId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

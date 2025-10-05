from dataclasses import dataclass
from src.domain.item.exception import MaxStackSizeValidationException


@dataclass(frozen=True)
class MaxStackSize:
    """スタックサイズの最大値を表す値オブジェクト"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise MaxStackSizeValidationException(value=self.value)

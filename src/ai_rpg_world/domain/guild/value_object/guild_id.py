from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.guild.exception.guild_exception import GuildIdValidationException


@dataclass(frozen=True)
class GuildId:
    """ギルドID値オブジェクト

    IDは正の整数である必要があります。既存の QuestId / PlayerId と同様の形式。
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise GuildIdValidationException(f"Guild ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "GuildId":
        """intまたはstrからGuildIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise GuildIdValidationException(value)
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GuildId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

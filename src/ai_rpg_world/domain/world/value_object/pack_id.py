"""
パック（群れ）を一意に識別する値オブジェクト。
同一 PackId を持つアクターは味方として扱い、スポットを跨いでも有効。
既存の Id 系（TradeId, PostId, WorldObjectId）と同様の create/例外/__str__ 仕様に統一。
"""

from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.world.exception.map_exception import PackIdValidationException


@dataclass(frozen=True)
class PackId:
    """群れを識別する不変のID（文字列値）"""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise PackIdValidationException(
                f"PackId value cannot be empty or whitespace: {repr(self.value)}"
            )

    @classmethod
    def create(cls, value: Union[str, int]) -> "PackId":
        """文字列または数値から PackId を生成する。None や空は不可。"""
        if value is None:
            raise PackIdValidationException("PackId value cannot be None")
        s = str(value).strip()
        if not s:
            raise PackIdValidationException(
                f"PackId value cannot be empty after strip: {repr(value)}"
            )
        return cls(s)

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PackId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

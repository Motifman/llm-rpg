"""板に注文を出せる主体 (経済統合 Phase 3)。

板にはエージェントの注文と商人の注文が並ぶ。**商人は世界の外との出入り口**で、
gold は無限に湧き、受け取った品は世界から消える (Phase 1 で商人の gold を
無限と決めたのと同じ一本の理由から出ている)。エージェントは世界の中の主体で、
持ち物も所持金も有限。

同じ「板の注文の出し手」でありながら決済の相手が根本的に違うので、片方を
Optional な player_id で表すと、決済のたびに None 判定が散らばる。どちらで
あるかを型で持つ。
"""

from dataclasses import dataclass
from enum import Enum

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketOrderValidationException,
)


class MarketParticipantKind(str, Enum):
    """注文の出し手の種別。"""

    PLAYER = "player"
    MERCHANT = "merchant"


@dataclass(frozen=True)
class MarketParticipant:
    """板の注文の出し手 1 人。"""

    kind: MarketParticipantKind
    entity_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MarketParticipantKind):
            raise MarketOrderValidationException(
                f"kind は MarketParticipantKind で指定してください (got {self.kind!r})"
            )
        if isinstance(self.entity_id, bool) or not isinstance(self.entity_id, int):
            raise MarketOrderValidationException(
                f"entity_id は整数で指定してください (got {self.entity_id!r})"
            )

    @classmethod
    def player(cls, player_id: PlayerId) -> "MarketParticipant":
        return cls(kind=MarketParticipantKind.PLAYER, entity_id=int(player_id))

    @classmethod
    def merchant(cls, merchant_id: int) -> "MarketParticipant":
        return cls(kind=MarketParticipantKind.MERCHANT, entity_id=int(merchant_id))

    @property
    def is_merchant(self) -> bool:
        return self.kind is MarketParticipantKind.MERCHANT

    @property
    def is_player(self) -> bool:
        return self.kind is MarketParticipantKind.PLAYER

    @property
    def player_id(self) -> PlayerId:
        """エージェントとしての ID。商人に対して呼ぶのは誤り。"""
        if not self.is_player:
            raise MarketOrderValidationException(
                "商人は PlayerId を持ちません (決済の相手を取り違えています)"
            )
        return PlayerId(self.entity_id)

"""取引イベント用の観測 formatter。"""

from typing import TYPE_CHECKING, Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter


class TradeObservationFormatter:
    """TradeOfferedEvent / TradeAcceptedEvent / TradeCancelledEvent を処理する。"""

    def __init__(self, parent: "ObservationFormatter") -> None:
        self._parent = parent

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        return self._parent._format_trade_event(event, recipient_player_id)

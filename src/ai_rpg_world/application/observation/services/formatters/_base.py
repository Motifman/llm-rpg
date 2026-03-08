"""小 formatter 共通インターフェース。"""

from typing import Any, Optional, Protocol

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class IObservationSubFormatter(Protocol):
    """個別イベント種別向け formatter の契約。"""

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """イベントを観測出力に変換。対象外なら None。"""
        ...

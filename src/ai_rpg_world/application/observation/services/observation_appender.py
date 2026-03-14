"""バッファへの観測追加と game_time_label 付与を行うサービス"""

from datetime import datetime
from typing import Optional

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationAppender:
    """
    観測エントリを構築し、バッファに append する。
    occurred_at と game_time_label を付与した ObservationEntry を作成して buffer に渡す。
    """

    def __init__(self, buffer: IObservationContextBuffer) -> None:
        self._buffer = buffer

    def append(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
        occurred_at: datetime,
        game_time_label: Optional[str] = None,
    ) -> None:
        """
        指定プレイヤーに観測エントリを追加する。
        ObservationEntry を構築して buffer.append に委譲する。
        """
        entry = ObservationEntry(
            occurred_at=occurred_at,
            output=output,
            game_time_label=game_time_label,
        )
        self._buffer.append(player_id, entry)

"""バッファへの観測追加と game_time_label 付与を行うサービス"""

from datetime import datetime
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
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

    def __init__(
        self,
        buffer: IObservationContextBuffer,
        runtime_context_provider: Optional[
            Callable[[PlayerId], Optional[ToolRuntimeContextDto]]
        ] = None,
    ) -> None:
        self._buffer = buffer
        self._runtime_context_provider = runtime_context_provider
        if runtime_context_provider is not None and not callable(runtime_context_provider):
            raise TypeError("runtime_context_provider must be callable or None")

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
        rtc = (
            self._runtime_context_provider(player_id)
            if self._runtime_context_provider is not None
            else None
        )
        self._buffer.append(player_id, entry, runtime_context=rtc)

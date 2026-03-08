"""Reflection の実行境界（cursor）を in-memory で保持するポート実装。

次フェーズで永続化する場合は IReflectionStatePort の永続化実装に差し替える。
"""

from datetime import datetime
from typing import Dict, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IReflectionStatePort
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryReflectionStatePort(IReflectionStatePort):
    """Reflection 境界をメモリ上で保持。永続化は次フェーズで差し替え可能。"""

    def __init__(self) -> None:
        self._last_game_day: Dict[int, int] = {}
        self._last_cursor: Dict[int, datetime] = {}

    def get_last_reflection_game_day(self, player_id: PlayerId) -> Optional[int]:
        return self._last_game_day.get(player_id.value)

    def get_reflection_cursor(self, player_id: PlayerId) -> Optional[datetime]:
        return self._last_cursor.get(player_id.value)

    def mark_reflection_success(
        self, player_id: PlayerId, game_day: int, cursor: datetime
    ) -> None:
        self._last_game_day[player_id.value] = game_day
        self._last_cursor[player_id.value] = cursor

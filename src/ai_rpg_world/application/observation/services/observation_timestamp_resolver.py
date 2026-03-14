"""イベントの occurred_at とゲーム内時刻ラベルを解決するサービス"""

from datetime import datetime
from typing import Any, Optional

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)


class ObservationTimestampResolver:
    """
    イベントから発生日時（occurred_at）とゲーム内時刻ラベルを解決する。
    game_time_provider と world_time_config が未設定の場合は game_time_label は None。
    """

    def __init__(
        self,
        game_time_provider: Optional[GameTimeProvider] = None,
        world_time_config: Optional[WorldTimeConfigService] = None,
    ) -> None:
        self._game_time_provider = game_time_provider
        self._world_time_config = world_time_config

    def resolve_occurred_at(self, event: Any) -> datetime:
        """イベントの発生日時を返す。属性が無い場合は現在時刻。"""
        occurred_at = getattr(event, "occurred_at", None)
        if occurred_at is None:
            return datetime.now()
        return occurred_at

    def resolve_game_time_label(self, event: Any) -> Optional[str]:
        """
        イベント発生時刻に対応するゲーム内時刻ラベルを返す。
        game_time_provider または world_time_config が未設定の場合は None。
        """
        if self._game_time_provider is None or self._world_time_config is None:
            return None
        from ai_rpg_world.domain.world.value_object.game_date_time import (
            game_date_time_from_tick,
        )

        occurred_tick = getattr(event, "occurred_tick", None)
        tick = occurred_tick or self._game_time_provider.get_current_tick()
        ticks_per_day = self._world_time_config.get_ticks_per_day()
        days_per_month = self._world_time_config.get_days_per_month()
        months_per_year = self._world_time_config.get_months_per_year()
        game_dt = game_date_time_from_tick(
            tick.value, ticks_per_day, days_per_month, months_per_year
        )
        return game_dt.format_for_display()

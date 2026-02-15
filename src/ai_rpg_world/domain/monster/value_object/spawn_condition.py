"""スポーン・リスポーン条件を表す値オブジェクト"""

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


@dataclass(frozen=True)
class SpawnCondition:
    """
    スポーン／リスポーンを実行する条件。
    現状は時間帯（time_band）のみ。将来 weather_tags や max_players_nearby 等を追加可能。
    """
    time_band: Optional[TimeOfDay] = None

    def is_satisfied_at(self, time_of_day: TimeOfDay) -> bool:
        """
        指定の時間帯で条件を満たすかどうかを返す。

        Args:
            time_of_day: 現在の時間帯

        Returns:
            条件を満たす場合 True。time_band が None の場合は常に True。
        """
        if self.time_band is None:
            return True
        return time_of_day == self.time_band

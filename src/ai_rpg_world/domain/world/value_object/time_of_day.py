"""
時間帯（TimeOfDay）の値オブジェクトと純粋関数。
tick と 1 日の tick 数から現在の時間帯を導く。
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.enum.monster_enum import ActiveTimeType


class TimeOfDay(Enum):
    """1日の中の時間帯"""
    MORNING = "MORNING"   # 朝
    DAY = "DAY"           # 昼
    EVENING = "EVENING"   # 夕
    NIGHT = "NIGHT"       # 夜


def time_of_day_from_tick(tick_value: int, ticks_per_day: int) -> TimeOfDay:
    """
    tick 値と 1 日あたりの tick 数から現在の時間帯を返す純粋関数。

    1日を 4 等分: 0-25% NIGHT, 25-50% MORNING, 50-75% DAY, 75-100% EVENING

    Args:
        tick_value: 現在のワールドティック値
        ticks_per_day: 1日を表すティック数（正の整数）

    Returns:
        現在の時間帯

    Raises:
        ValueError: ticks_per_day が 1 未満の場合
    """
    if ticks_per_day < 1:
        raise ValueError(f"ticks_per_day must be positive: {ticks_per_day}")
    t = tick_value % ticks_per_day
    quarter = ticks_per_day // 4
    if t < quarter:
        return TimeOfDay.NIGHT
    if t < 2 * quarter:
        return TimeOfDay.MORNING
    if t < 3 * quarter:
        return TimeOfDay.DAY
    return TimeOfDay.EVENING


def is_active_at_time(active_time: "ActiveTimeType", time_of_day: TimeOfDay) -> bool:
    """
    活動時間タイプが指定の時間帯に活動するかどうかを返す純粋関数。

    Args:
        active_time: 活動時間タイプ（昼行性・夜行性など）
        time_of_day: 現在の時間帯

    Returns:
        活動する場合は True
    """
    from ai_rpg_world.domain.monster.enum.monster_enum import ActiveTimeType
    if active_time == ActiveTimeType.ALWAYS:
        return True
    if active_time == ActiveTimeType.DIURNAL:
        return time_of_day == TimeOfDay.DAY
    if active_time == ActiveTimeType.NOCTURNAL:
        return time_of_day == TimeOfDay.NIGHT
    if active_time == ActiveTimeType.CREPUSCULAR:
        return time_of_day in (TimeOfDay.MORNING, TimeOfDay.EVENING)
    return True

"""
ゲーム内日時（年・月・日・時・分・秒）の値オブジェクトと純粋関数。
ワールドティックと設定（1日のティック数・1か月の日数・1年の月数）から人間向けの日時を導く。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameDateTime:
    """
    ゲーム内の日時を表す値オブジェクト。
    年・月・日・時・分・秒は 1 始まり（人間の表記に合わせる）。
    """

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int

    def __post_init__(self) -> None:
        if self.year < 1:
            raise ValueError(f"year must be positive: {self.year}")
        if self.month < 1:
            raise ValueError(f"month must be positive: {self.month}")
        if self.day < 1:
            raise ValueError(f"day must be positive: {self.day}")
        if not 0 <= self.hour <= 23:
            raise ValueError(f"hour must be 0-23: {self.hour}")
        if not 0 <= self.minute <= 59:
            raise ValueError(f"minute must be 0-59: {self.minute}")
        if not 0 <= self.second <= 59:
            raise ValueError(f"second must be 0-59: {self.second}")

    def format_for_display(self) -> str:
        """LLM やログ向けの人間可読文字列（例: 1年2月3日 12:30:45）を返す。"""
        return (
            f"{self.year}年{self.month}月{self.day}日 "
            f"{self.hour:02d}:{self.minute:02d}:{self.second:02d}"
        )


def game_date_time_from_tick(
    tick_value: int,
    ticks_per_day: int,
    days_per_month: int = 30,
    months_per_year: int = 12,
) -> GameDateTime:
    """
    ワールドティックからゲーム内日時を計算する純粋関数。

    1日 = ticks_per_day ティック。1日の中は 0..ticks_per_day-1 を
    0:00:00 ～ 23:59:59 の秒に線形マップする。
    暦は 1 年 = months_per_year 月、1 月 = days_per_month 日で、
    日数が経過するごとに日→月→年を繰り上げる。年・月・日は 1 始まり。

    Args:
        tick_value: 現在のワールドティック値（0 以上を想定）
        ticks_per_day: 1日を表すティック数（正の整数）
        days_per_month: 1か月を表す日数（正の整数）
        months_per_year: 1年を表す月数（正の整数）

    Returns:
        対応する GameDateTime

    Raises:
        ValueError: いずれかの設定が 1 未満の場合
    """
    if ticks_per_day < 1:
        raise ValueError(f"ticks_per_day must be positive: {ticks_per_day}")
    if days_per_month < 1:
        raise ValueError(f"days_per_month must be positive: {days_per_month}")
    if months_per_year < 1:
        raise ValueError(f"months_per_year must be positive: {months_per_year}")

    # 負のティックは 0 として扱う（履歴互換のため）
    effective_tick = max(0, tick_value)

    day_index = effective_tick // ticks_per_day
    tick_within_day = effective_tick % ticks_per_day

    # 1日 = 86400 秒にマップ
    seconds_in_day = (tick_within_day * 86400) // ticks_per_day
    if seconds_in_day >= 86400:
        seconds_in_day = 86399
    hour = seconds_in_day // 3600
    remainder = seconds_in_day % 3600
    minute = remainder // 60
    second = remainder % 60

    days_per_year = days_per_month * months_per_year
    year = day_index // days_per_year + 1
    day_in_year = day_index % days_per_year
    month = day_in_year // days_per_month + 1
    day = day_in_year % days_per_month + 1

    return GameDateTime(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
    )

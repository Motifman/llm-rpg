"""
ヘイト（アグロ）の記憶ポリシー。
モンスターごとに「いつまで覚えているか」「復讐対象を忘れないか」などを表現する。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AggroMemoryPolicy:
    """
    ヘイトの忘却ポリシー。
    最後にターゲットを見かけた時刻（last_seen_tick）から current_tick までの経過で、
    有効/忘却を判定する。時間軸はグローバル tick 一つ。
    """

    forget_after_ticks: Optional[int] = None
    """この tick 数だけ「見かけない」と忘却。None の場合は忘れない（一生覚える）。"""

    revenge_never_forget: bool = False
    """True の場合、自分を瀕死にした相手などは忘却対象から外す（将来拡張用）。"""

    def __post_init__(self) -> None:
        if self.forget_after_ticks is not None and self.forget_after_ticks < 0:
            raise ValueError(
                f"forget_after_ticks must be non-negative or None, got {self.forget_after_ticks}"
            )

    def is_forgotten(self, current_tick: int, last_seen_tick: int) -> bool:
        """
        最後に見かけた時刻から経過で忘却したか判定する。

        Args:
            current_tick: 現在のグローバル tick
            last_seen_tick: 最後にそのターゲットを見かけた tick

        Returns:
            True なら忘却済み（ヘイトを無効とする）
        """
        if self.forget_after_ticks is None:
            return False
        elapsed = current_tick - last_seen_tick
        return elapsed > self.forget_after_ticks

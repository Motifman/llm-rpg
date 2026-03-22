"""ゲーム内で同時にアクティブにできるアプリは高々 1 つ（active app slot）。"""

from enum import Enum


class GameAppKind(str, Enum):
    """現在フォアグラウンドのアプリ種別。"""

    NONE = "none"
    SNS = "sns"
    TRADE = "trade"


__all__ = ["GameAppKind"]

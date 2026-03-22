"""取引所仮想ページの種別・タブ（LLM 向け契約と一致する文字列値）。"""

from enum import Enum


class TradeVirtualPageKind(str, Enum):
    """画面種別。スナップショット JSON・ツール引数ではこの値を用いる。"""

    MARKET = "market"
    SEARCH = "search"
    MY_TRADES = "my_trades"


class MyTradesTab(str, Enum):
    """my_trades 画面のタブ。"""

    SELLING = "selling"
    INCOMING = "incoming"


__all__ = ["TradeVirtualPageKind", "MyTradesTab"]

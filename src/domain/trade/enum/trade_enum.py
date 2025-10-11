from enum import Enum


class TradeType(Enum):
    GLOBAL = "global"     # グローバル取引所
    DIRECT = "direct"     # 直接取引（同一Spot）


class TradeStatus(Enum):
    ACTIVE = "active"         # 募集中
    COMPLETED = "completed"   # 成立
    CANCELLED = "cancelled"   # キャンセル

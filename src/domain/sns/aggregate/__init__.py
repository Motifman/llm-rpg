"""
SNSドメインの集約

集約は一貫性の境界を持ち、AggregateRootを継承します。
"""

from .base_sns_aggregate import BaseSnsContentAggregate
from .post_aggregate import PostAggregate
from .reply_aggregate import ReplyAggregate
from .user_aggregate import UserAggregate

__all__ = [
    "BaseSnsContentAggregate",
    "PostAggregate",
    "ReplyAggregate",
    "UserAggregate",
]

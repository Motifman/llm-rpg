"""
SNSドメインのエンティティ

エンティティはIDを持ち、ライフサイクルがあるオブジェクトです。
"""

from .notification import Notification
from .sns_user import SnsUser

__all__ = [
    "Notification",
    "SnsUser",
]

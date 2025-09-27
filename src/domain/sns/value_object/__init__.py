"""
SNSドメインの値オブジェクト

値オブジェクトは不変性を保ち、属性で識別されるオブジェクトです。
"""

from .block import BlockRelationShip
from .follow import FollowRelationShip
from .like import Like
from .mention import Mention
from .post_content import PostContent
from .post_id import PostId
from .reply_id import ReplyId
from .subscribe import SubscribeRelationShip
from .user_id import UserId
from .user_profile import UserProfile

__all__ = [
    "BlockRelationShip",
    "FollowRelationShip",
    "Like",
    "Mention",
    "PostContent",
    "PostId",
    "ReplyId",
    "SubscribeRelationShip",
    "UserId",
    "UserProfile",
]

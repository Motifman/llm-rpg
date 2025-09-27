from enum import Enum


class PostVisibility(Enum):
    """投稿の公開範囲"""
    PUBLIC = "public"
    FOLLOWERS_ONLY = "followers_only"
    PRIVATE = "private"


class UserRelationshipType(Enum):
    """ユーザー関係性の種類"""
    FOLLOWEES = "followees"
    FOLLOWERS = "followers"
    BLOCKED_USERS = "blocked_users"
    BLOCKERS = "blockers"
    SUBSCRIPTIONS = "subscriptions"
    SUBSCRIBERS = "subscribers"
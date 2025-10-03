"""
SNSドメインのユーザー関係性関連例外
"""

from src.domain.sns.exception.base_exceptions import UserRelationshipException


class FollowException(UserRelationshipException):
    """フォロー関連の例外"""
    error_code = "FOLLOW_ERROR"


class CannotFollowBlockedUserException(FollowException):
    """ブロックされたユーザーをフォローしようとした場合の例外"""
    error_code = "CANNOT_FOLLOW_BLOCKED_USER"

    def __init__(self, follower_user_id: int, followee_user_id: int, message: str = None):
        self.follower_user_id = follower_user_id
        self.followee_user_id = followee_user_id
        if message is None:
            message = f"ユーザーをフォローできません。ブロックされているユーザーです。follower_id: {follower_user_id}, followee_id: {followee_user_id}"
        super().__init__(message)


class CannotUnfollowNotFollowedUserException(FollowException):
    """フォローしていないユーザーのフォロー解除を試みた場合の例外"""
    error_code = "CANNOT_UNFOLLOW_NOT_FOLLOWED_USER"

    def __init__(self, follower_user_id: int, followee_user_id: int, message: str = None):
        self.follower_user_id = follower_user_id
        self.followee_user_id = followee_user_id
        if message is None:
            message = f"ユーザーのフォロー解除ができません。フォローしていないユーザーです。follower_id: {follower_user_id}, followee_id: {followee_user_id}"
        super().__init__(message)


class BlockException(UserRelationshipException):
    """ブロック関連の例外"""
    error_code = "BLOCK_ERROR"


class CannotBlockAlreadyBlockedUserException(BlockException):
    """既にブロックしているユーザーをブロックしようとした場合の例外"""
    error_code = "CANNOT_BLOCK_ALREADY_BLOCKED_USER"

    def __init__(self, blocker_user_id: int, blocked_user_id: int, message: str = None):
        self.blocker_user_id = blocker_user_id
        self.blocked_user_id = blocked_user_id
        if message is None:
            message = f"ユーザーをブロックできません。既にブロックしているユーザーです。blocker_id: {blocker_user_id}, blocked_id: {blocked_user_id}"
        super().__init__(message)


class CannotUnblockNotBlockedUserException(BlockException):
    """ブロックしていないユーザーのブロック解除を試みた場合の例外"""
    error_code = "CANNOT_UNBLOCK_NOT_BLOCKED_USER"

    def __init__(self, blocker_user_id: int, blocked_user_id: int, message: str = None):
        self.blocker_user_id = blocker_user_id
        self.blocked_user_id = blocked_user_id
        if message is None:
            message = f"ユーザーのブロック解除ができません。ブロックしていないユーザーです。blocker_id: {blocker_user_id}, blocked_id: {blocked_user_id}"
        super().__init__(message)


class SubscribeException(UserRelationshipException):
    """購読関連の例外"""
    error_code = "SUBSCRIBE_ERROR"


class CannotSubscribeAlreadySubscribedUserException(SubscribeException):
    """既に購読しているユーザーを購読しようとした場合の例外"""
    error_code = "CANNOT_SUBSCRIBE_ALREADY_SUBSCRIBED_USER"

    def __init__(self, subscriber_user_id: int, subscribed_user_id: int, message: str = None):
        self.subscriber_user_id = subscriber_user_id
        self.subscribed_user_id = subscribed_user_id
        if message is None:
            message = f"ユーザーを購読できません。既に購読しているユーザーです。subscriber_id: {subscriber_user_id}, subscribed_id: {subscribed_user_id}"
        super().__init__(message)


class CannotSubscribeBlockedUserException(SubscribeException):
    """ブロックされたユーザーを購読しようとした場合の例外"""
    error_code = "CANNOT_SUBSCRIBE_BLOCKED_USER"

    def __init__(self, subscriber_user_id: int, subscribed_user_id: int, message: str = None):
        self.subscriber_user_id = subscriber_user_id
        self.subscribed_user_id = subscribed_user_id
        if message is None:
            message = f"ユーザーを購読できません。ブロックされているユーザーです。subscriber_id: {subscriber_user_id}, subscribed_id: {subscribed_user_id}"
        super().__init__(message)


class CannotSubscribeNotFollowedUserException(SubscribeException):
    """フォローしていないユーザーを購読しようとした場合の例外"""
    error_code = "CANNOT_SUBSCRIBE_NOT_FOLLOWED_USER"

    def __init__(self, subscriber_user_id: int, subscribed_user_id: int, message: str = None):
        self.subscriber_user_id = subscriber_user_id
        self.subscribed_user_id = subscribed_user_id
        if message is None:
            message = f"ユーザーを購読できません。フォローしていないユーザーです。subscriber_id: {subscriber_user_id}, subscribed_id: {subscribed_user_id}"
        super().__init__(message)


class CannotUnsubscribeNotSubscribedUserException(SubscribeException):
    """購読していないユーザーの購読解除を試みた場合の例外"""
    error_code = "CANNOT_UNSUBSCRIBE_NOT_SUBSCRIBED_USER"

    def __init__(self, subscriber_user_id: int, subscribed_user_id: int, message: str = None):
        self.subscriber_user_id = subscriber_user_id
        self.subscribed_user_id = subscribed_user_id
        if message is None:
            message = f"ユーザーの購読解除ができません。購読していないユーザーです。subscriber_id: {subscriber_user_id}, subscribed_id: {subscribed_user_id}"
        super().__init__(message)


class RelationshipValidationException(UserRelationshipException):
    """関係性バリデーション関連の例外"""
    error_code = "RELATIONSHIP_VALIDATION_ERROR"


class PositiveUserIdValidationException(RelationshipValidationException):
    """ユーザーIDが正の数値でない場合の例外(Deprecated: ユーザーIDバリデーション例外に置き換えられたため、削除予定)"""
    error_code = "POSITIVE_USER_ID_VALIDATION_ERROR"

    def __init__(self, user_id: int, field_name: str, message: str = None):
        self.user_id = user_id
        self.field_name = field_name
        if message is None:
            message = f"{field_name} must be positive. {field_name}: {user_id}"
        super().__init__(message)


class SelfReferenceValidationException(RelationshipValidationException):
    """自分自身を参照しようとした場合の例外"""
    error_code = "SELF_REFERENCE_VALIDATION_ERROR"

    def __init__(self, user_id: int, field_name1: str, field_name2: str, message: str = None):
        self.user_id = user_id
        self.field_name1 = field_name1
        self.field_name2 = field_name2
        if message is None:
            message = f"{field_name1} and {field_name2} must be different. Both are: {user_id}"
        super().__init__(message)


class SelfFollowException(FollowException):
    """自分自身をフォローしようとした場合の例外"""
    error_code = "SELF_FOLLOW_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身をフォローすることはできません。user_id: {user_id}"
        super().__init__(message)


class SelfUnfollowException(FollowException):
    """自分自身をアンフォローしようとした場合の例外"""
    error_code = "SELF_UNFOLLOW_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身をアンフォローすることはできません。user_id: {user_id}"
        super().__init__(message)


class SelfBlockException(BlockException):
    """自分自身をブロックしようとした場合の例外"""
    error_code = "SELF_BLOCK_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身をブロックすることはできません。user_id: {user_id}"
        super().__init__(message)


class SelfUnblockException(BlockException):
    """自分自身をアンブロックしようとした場合の例外"""
    error_code = "SELF_UNBLOCK_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身をアンブロックすることはできません。user_id: {user_id}"
        super().__init__(message)


class SelfSubscribeException(SubscribeException):
    """自分自身を購読しようとした場合の例外"""
    error_code = "SELF_SUBSCRIBE_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身を購読することはできません。user_id: {user_id}"
        super().__init__(message)


class SelfUnsubscribeException(SubscribeException):
    """自分自身をアンサブスクライブしようとした場合の例外"""
    error_code = "SELF_UNSUBSCRIBE_ERROR"

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"自分自身をアンサブスクライブすることはできません。user_id: {user_id}"
        super().__init__(message)

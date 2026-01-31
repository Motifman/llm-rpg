"""
SNSドメインのコンテンツ関連例外
"""

from ai_rpg_world.domain.sns.exception.base_exceptions import ContentValidationException, ContentTypeException, SnsDomainException


class InvalidContentTypeException(ContentValidationException):
    """コンテンツタイプが無効な場合の例外"""
    error_code = "INVALID_CONTENT_TYPE"

    def __init__(self, content_type: str, message: str = None):
        self.content_type = content_type
        if message is None:
            message = f"コンテンツタイプは「post」または「reply」である必要があります。入力値: 「{content_type}」"
        super().__init__(message)


class InvalidParentReferenceException(ContentValidationException):
    """親参照が無効な場合の例外"""
    error_code = "INVALID_PARENT_REFERENCE"

    def __init__(self, message: str = None):
        if message is None:
            message = "親ポストIDと親リプライIDを同時に設定することはできません。"
        super().__init__(message)


class PostIdValidationException(ContentValidationException):
    """ポストIDバリデーション例外"""
    error_code = "POST_ID_VALIDATION_ERROR"

    def __init__(self, post_id: int, message: str = None):
        self.post_id = post_id
        if message is None:
            message = f"ポストIDは正の数値である必要があります。入力値: {post_id}"
        super().__init__(message)


class ReplyIdValidationException(ContentValidationException):
    """リプライIDバリデーション例外"""
    error_code = "REPLY_ID_VALIDATION_ERROR"

    def __init__(self, reply_id: int, message: str = None):
        self.reply_id = reply_id
        if message is None:
            message = f"リプライIDは正の数値である必要があります。入力値: {reply_id}"
        super().__init__(message)


class ContentLengthValidationException(ContentValidationException):
    """コンテンツ文字数バリデーション例外"""
    error_code = "CONTENT_LENGTH_VALIDATION_ERROR"

    def __init__(self, content: str, max_length: int, message: str = None):
        self.content = content
        self.max_length = max_length
        if message is None:
            message = f"コンテンツは{max_length}文字以内でなければなりません。現在の文字数: {len(content)}"
        super().__init__(message)


class HashtagCountValidationException(ContentValidationException):
    """ハッシュタグ数バリデーション例外"""
    error_code = "HASHTAG_COUNT_VALIDATION_ERROR"

    def __init__(self, hashtag_count: int, max_count: int, message: str = None):
        self.hashtag_count = hashtag_count
        self.max_count = max_count
        if message is None:
            message = f"ハッシュタグは{max_count}個以内でなければなりません。現在の個数: {hashtag_count}"
        super().__init__(message)


class VisibilityValidationException(ContentValidationException):
    """可視性バリデーション例外"""
    error_code = "VISIBILITY_VALIDATION_ERROR"

    def __init__(self, visibility: str, message: str = None):
        self.visibility = visibility
        if message is None:
            message = f"可視性は有効な値である必要があります。入力値: '{visibility}'"
        super().__init__(message)


class MentionValidationException(ContentValidationException):
    """メンションバリデーション例外"""
    error_code = "MENTION_VALIDATION_ERROR"

    def __init__(self, user_name: str, message: str = None):
        self.user_name = user_name
        if message is None:
            message = f"メンションするユーザー名は必須です。入力値: '{user_name}'"
        super().__init__(message)


class ContentOwnershipException(SnsDomainException):
    """コンテンツ所有権関連の例外"""
    error_code = "CONTENT_OWNERSHIP_ERROR"

    def __init__(self, user_id: int, content_id: int, content_type: str, message: str = None):
        self.user_id = user_id
        self.content_id = content_id
        self.content_type = content_type
        if message is None:
            message = f"ユーザーはこの{content_type}を削除する権限がありません。user_id: {user_id}, content_id: {content_id}"
        super().__init__(message)


# 後方互換性のためのエイリアス
OwnershipException = ContentOwnershipException


class ContentTypeMismatchException(ContentTypeException):
    """コンテンツタイプ関連の例外"""
    error_code = "CONTENT_TYPE_MISMATCH_ERROR"

    def __init__(self, content_id: int, expected_type: str, actual_type: str, message: str = None):
        self.content_id = content_id
        self.expected_type = expected_type
        self.actual_type = actual_type
        if message is None:
            message = f"コンテンツIDは「{expected_type}」である必要があります。実際のタイプ: 「{actual_type}」、content_id: {content_id}"
        super().__init__(message)


class ContentAlreadyDeletedException(ContentValidationException):
    """すでに削除済みのコンテンツを削除しようとした場合の例外"""
    error_code = "CONTENT_ALREADY_DELETED"

    def __init__(self, content_id: int, content_type: str, message: str = None):
        self.content_id = content_id
        self.content_type = content_type
        if message is None:
            message = f"すでに削除済みの{content_type}は削除できません。content_id: {content_id}"
        super().__init__(message)


class NotificationIdValidationException(ContentValidationException):
    """通知IDバリデーション例外"""
    error_code = "NOTIFICATION_ID_VALIDATION_ERROR"

    def __init__(self, notification_id, message: str = None):
        self.notification_id = notification_id
        if message is None:
            message = f"通知IDは正の数値である必要があります。入力値: {notification_id}"
        super().__init__(message)


class NotificationContentValidationException(ContentValidationException):
    """通知コンテンツバリデーション例外"""
    error_code = "NOTIFICATION_CONTENT_VALIDATION_ERROR"

    def __init__(self, message: str):
        super().__init__(message)

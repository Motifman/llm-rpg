"""
SNSドメインのユーザープロファイル関連例外
"""

from src.domain.sns.exception.base_exceptions import UserProfileException


class UserNotFoundException(UserProfileException):
    """ユーザーが見つからない場合の例外"""

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"ユーザーが見つかりません: {user_id}"
        super().__init__(message)


class UserIdValidationException(UserProfileException):
    """ユーザーIDバリデーション例外"""

    def __init__(self, user_id: int, message: str = None):
        self.user_id = user_id
        if message is None:
            message = f"ユーザーIDは正の数値である必要があります。入力値: {user_id}"
        super().__init__(message)


class UserNameValidationException(UserProfileException):
    """ユーザー名バリデーション例外"""

    def __init__(self, user_name: str, message: str = None):
        self.user_name = user_name
        if message is None:
            message = f"ユーザー名は3-20文字である必要があります。入力値: '{user_name}' (長さ: {len(user_name)})"
        super().__init__(message)


class DisplayNameValidationException(UserProfileException):
    """表示名バリデーション例外"""

    def __init__(self, display_name: str, message: str = None):
        self.display_name = display_name
        if message is None:
            message = f"表示名は1-30文字である必要があります。入力値: '{display_name}' (長さ: {len(display_name)})"
        super().__init__(message)


class BioValidationException(UserProfileException):
    """Bioバリデーション例外"""

    def __init__(self, bio: str, message: str = None):
        self.bio = bio
        if message is None:
            message = f"Bioは200文字以内である必要があります。入力値の長さ: {len(bio)}"
        super().__init__(message)


class ProfileUpdateValidationException(UserProfileException):
    """プロフィール更新時のバリデーション例外"""

    def __init__(self, message: str = None):
        if message is None:
            message = "プロフィール更新時には少なくとも1つのフィールドを指定する必要があります。"
        super().__init__(message)

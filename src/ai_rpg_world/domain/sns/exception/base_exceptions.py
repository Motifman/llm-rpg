"""
SNSドメインの基底例外定義

DDDの観点では、ドメイン層で汎用的なValueErrorを使用せず、
ドメイン固有の意味を持つカスタム例外を使用すべきです。
これにより、ビジネスルールの明確化、テストの容易性、
適切なエラーハンドリングが可能になります。
"""


class SnsDomainException(Exception):
    """SNSドメインの基底例外"""
    error_code: str = "DOMAIN_ERROR"


class UserProfileException(SnsDomainException):
    """ユーザープロファイル関連の例外"""
    pass


class UserRelationshipException(SnsDomainException):
    """ユーザー関係性関連の例外"""
    pass


class ContentValidationException(SnsDomainException):
    """コンテンツ関連のバリデーション例外"""
    pass


class ContentTypeException(SnsDomainException):
    """コンテンツタイプ関連の例外"""
    pass

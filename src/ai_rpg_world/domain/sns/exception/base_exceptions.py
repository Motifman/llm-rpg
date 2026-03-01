"""
SNSドメインの基底例外定義

DDDの観点では、ドメイン層で汎用的なValueErrorを使用せず、
ドメイン固有の意味を持つカスタム例外を使用すべきです。
これにより、ビジネスルールの明確化、テストの容易性、
適切なエラーハンドリングが可能になります。

共通のドメイン例外契約に合わせ、DomainException を継承します。
"""

from ai_rpg_world.domain.common.exception import DomainException


class SnsDomainException(DomainException):
    """SNSドメインの基底例外。共通の DomainException を継承する。"""
    domain: str = "sns"
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

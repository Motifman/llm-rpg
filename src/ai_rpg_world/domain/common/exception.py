"""
ドメイン層の共通例外定義

全てのドメイン例外の基底となる例外クラスを定義します。
DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用することで、
ビジネスルールの明確化、テストの容易性、適切なエラーハンドリングを実現します。
"""

from enum import Enum


class DomainErrorCategory(str, Enum):
    """ドメイン例外のカテゴリ"""
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    BUSINESS_RULE = "business_rule"
    STATE = "state"


class DomainException(Exception):
    """全てのドメイン例外の共通基底クラス

    全てのドメイン例外はこのクラスを継承し、
    ドメイン名、エラーコード、カテゴリを持つべきです。
    """
    domain: str = "common"
    error_code: str = "DOMAIN_ERROR"
    category: DomainErrorCategory = DomainErrorCategory.STATE

    def __init__(self, message: str = None, **kwargs):
        """初期化

        Args:
            message: エラーメッセージ（オプション）
            **kwargs: 追加のコンテキスト情報
        """
        self.context = kwargs
        if message is None:
            message = f"{self.error_code}: {self.category.value}"
        super().__init__(message)


# カテゴリ別の抽象例外クラス

class ValidationException(DomainException):
    """バリデーション関連の例外

    値の検証に失敗した場合に使用します。
    エンティティや値オブジェクトの構築時、メソッド引数の検証などで発生します。
    """
    category = DomainErrorCategory.VALIDATION


class NotFoundException(DomainException):
    """存在確認関連の例外

    リポジトリからの検索などで対象が見つからない場合に使用します。
    """
    category = DomainErrorCategory.NOT_FOUND


class BusinessRuleException(DomainException):
    """ビジネスルール違反関連の例外

    ドメインのビジネスルールに違反する場合に使用します。
    例: 材料不足、権限不足、状態制約など
    """
    category = DomainErrorCategory.BUSINESS_RULE


class StateException(DomainException):
    """状態関連の例外

    エンティティの状態遷移が無効な場合や、
    整合性の破壊を防ぐために使用します。
    """
    category = DomainErrorCategory.STATE

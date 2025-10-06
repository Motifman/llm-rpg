"""
Playerドメインの基底例外定義

DDDの観点では、ドメイン層で汎用的なValueErrorを使用せず、
ドメイン固有の意味を持つカスタム例外を使用すべきです。
これにより、ビジネスルールの明確化、テストの容易性、
適切なエラーハンドリングが可能になります。
"""


class PlayerDomainException(Exception):
    """Playerドメインの基底例外"""
    error_code: str = "PLAYER_DOMAIN_ERROR"

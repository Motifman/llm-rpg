from abc import ABC, abstractmethod


class CombatConfigService(ABC):
    """戦闘バランスに関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_critical_multiplier(self) -> float:
        """クリティカル時のダメージ倍率を取得"""
        pass

    @abstractmethod
    def get_minimum_damage(self) -> int:
        """最低保証ダメージ量を取得"""
        pass


class DefaultCombatConfigService(CombatConfigService):
    """デフォルトの戦闘設定実装"""

    def __init__(
        self,
        critical_multiplier: float = 1.5,
        minimum_damage: int = 1
    ):
        self._critical_multiplier = critical_multiplier
        self._minimum_damage = minimum_damage

    def get_critical_multiplier(self) -> float:
        return self._critical_multiplier

    def get_minimum_damage(self) -> int:
        return self._minimum_damage

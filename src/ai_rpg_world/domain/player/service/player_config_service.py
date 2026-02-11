from abc import ABC, abstractmethod


class PlayerConfigService(ABC):
    """プレイヤーの基本設定に関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_revive_hp_rate(self) -> float:
        """蘇生時のHP回復率（0.0〜1.0）を取得"""
        pass


class DefaultPlayerConfigService(PlayerConfigService):
    """デフォルトのプレイヤー設定実装"""

    def __init__(self, revive_hp_rate: float = 0.1):
        self._revive_hp_rate = revive_hp_rate

    def get_revive_hp_rate(self) -> float:
        return self._revive_hp_rate

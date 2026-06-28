from abc import ABC, abstractmethod


class PlayerConfigService(ABC):
    """プレイヤーの基本設定に関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_revive_hp_rate(self) -> float:
        """蘇生時のHP回復率（0.0〜1.0）を取得"""
        pass


class DefaultPlayerConfigService(PlayerConfigService):
    """デフォルトのプレイヤー設定実装"""

    def __init__(self, revive_hp_rate: float = 0.4):
        """default 0.4 = max_hp の 40% で復帰。Issue #621 で 0.1 → 0.4 に
        引き上げ: 旧 0.1 (= HP 10) では復活直後にも一撃で down する設計で、
        救援機構 (first_aid / tend_to_player) の意味が薄かった。
        """
        self._revive_hp_rate = revive_hp_rate

    def get_revive_hp_rate(self) -> float:
        return self._revive_hp_rate

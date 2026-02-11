from abc import ABC, abstractmethod


class MonsterConfigService(ABC):
    """モンスターの挙動に関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_regeneration_rate(self) -> float:
        """ティックあたりの自然回復率（0.0〜1.0）を取得"""
        pass


class DefaultMonsterConfigService(MonsterConfigService):
    """デフォルトのモンスター設定実装"""

    def __init__(self, regeneration_rate: float = 0.01):
        self._regeneration_rate = regeneration_rate

    def get_regeneration_rate(self) -> float:
        return self._regeneration_rate

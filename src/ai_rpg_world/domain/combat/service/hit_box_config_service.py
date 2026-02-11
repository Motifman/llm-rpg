from abc import ABC, abstractmethod


class HitBoxConfigService(ABC):
    """HitBoxシミュレーションに関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_substeps_per_tick(self) -> int:
        """1ティック内のHitBox更新サブステップ数を取得する"""
        pass


class DefaultHitBoxConfigService(HitBoxConfigService):
    """デフォルトのHitBox設定実装"""

    def __init__(self, substeps_per_tick: int = 4):
        # 0以下が渡っても安全に最低1へ丸める
        self._substeps_per_tick = max(1, substeps_per_tick)

    def get_substeps_per_tick(self) -> int:
        return self._substeps_per_tick

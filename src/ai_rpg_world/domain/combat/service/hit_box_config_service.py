from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate

class HitBoxConfigService(ABC):
    """HitBoxシミュレーションに関する設定値を提供するドメインサービス"""

    @abstractmethod
    def get_substeps_per_tick(self) -> int:
        """1ティック内のHitBox更新サブステップ数を取得する"""
        pass

    @abstractmethod
    def get_substeps_for_hit_box(self, hit_box: "HitBoxAggregate") -> int:
        """HitBox個体に応じた1ティック内サブステップ数を取得する"""
        pass

    @abstractmethod
    def get_max_collision_checks_per_tick(self) -> int:
        """1HitBoxあたり1ティック内で許容する衝突判定回数上限を取得する"""
        pass


class DefaultHitBoxConfigService(HitBoxConfigService):
    """デフォルトのHitBox設定実装"""

    def __init__(
        self,
        substeps_per_tick: int = 4,
        low_speed_substeps: int = 2,
        high_speed_substeps: int = 8,
        low_speed_threshold: float = 0.5,
        high_speed_threshold: float = 1.5,
        max_collision_checks_per_tick: int = 512,
    ):
        # 0以下が渡っても安全に最低1へ丸める
        self._substeps_per_tick = max(1, substeps_per_tick)
        self._low_speed_substeps = max(1, low_speed_substeps)
        self._high_speed_substeps = max(self._substeps_per_tick, high_speed_substeps)
        self._low_speed_threshold = max(0.0, low_speed_threshold)
        self._high_speed_threshold = max(self._low_speed_threshold, high_speed_threshold)
        self._max_collision_checks_per_tick = max(1, max_collision_checks_per_tick)

    def get_substeps_per_tick(self) -> int:
        return self._substeps_per_tick

    def get_substeps_for_hit_box(self, hit_box: "HitBoxAggregate") -> int:
        velocity = hit_box.velocity
        speed = max(abs(velocity.dx), abs(velocity.dy), abs(velocity.dz))

        if speed <= self._low_speed_threshold:
            return self._low_speed_substeps
        if speed >= self._high_speed_threshold:
            return self._high_speed_substeps
        return self._substeps_per_tick

    def get_max_collision_checks_per_tick(self) -> int:
        return self._max_collision_checks_per_tick

"""スポットグラフ用アプリケーションサービスの例外。"""

from __future__ import annotations

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.value_object import WorldTick


class SpotGraphSimulationException(ApplicationException):
    """スポットグラフのシミュレーション失敗。"""


class SpotGraphPostTickHookFailedException(SystemErrorException):
    """post-tick hook が失敗した。"""

    def __init__(
        self,
        current_tick: WorldTick,
        failed_hooks: tuple[str, ...],
        original_exception: Exception,
    ) -> None:
        super().__init__(
            f"spot_graph post-tick hooks failed at tick={current_tick.value}: {', '.join(failed_hooks)}",
            original_exception=original_exception,
        )
        self.current_tick = current_tick
        self.failed_hooks = failed_hooks


__all__ = [
    "SpotGraphPostTickHookFailedException",
    "SpotGraphSimulationException",
]

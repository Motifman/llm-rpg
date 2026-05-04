"""tick経過で欲求を自然増加させるステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で全プレイヤーの空腹・疲労を緩やかに増加させる。
"""

from __future__ import annotations

from typing import Dict

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


# デフォルトの増加レート（tick あたり）
DEFAULT_NEED_RATES: Dict[NeedType, int] = {
    NeedType.HUNGER: 1,   # 100tick で空腹が限界に達する
    NeedType.FATIGUE: 1,  # 100tick で疲労が限界に達する
}


class SpotGraphNeedsDecayStageService:
    """毎tick で全プレイヤーの欲求を自然増加させる。

    ``_SpotGraphTickStage`` Protocol に準拠。
    ``SpotGraphSimulationApplicationService`` の tick パイプラインに
    ``needs_decay_stage`` として注入する。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        *,
        rates: Dict[NeedType, int] | None = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._rates = rates or dict(DEFAULT_NEED_RATES)

    def run(self, current_tick: WorldTick) -> None:
        """全プレイヤーの欲求を増加させ、一括保存する。"""
        updated = []
        for status in self._player_status_repository.find_all():
            # ダウン中は欲求の自然増加を停止（蘇生後に蓄積しない設計）
            if not status.can_act():
                continue
            if len(status.needs) == 0:
                continue
            changed = False
            for need_type, rate in self._rates.items():
                if rate <= 0:
                    continue
                need = status.needs.get(need_type)
                if need is not None and need.value < need.max_value:
                    status.increase_need(need_type, rate)
                    changed = True
            if changed:
                updated.append(status)
        if updated:
            self._player_status_repository.save_all(updated)

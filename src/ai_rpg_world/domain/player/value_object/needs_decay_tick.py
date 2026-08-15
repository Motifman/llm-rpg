"""欲求の tick 経過による自然増加と限界ダメージの設定値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_rpg_world.domain.player.value_object.agent_need import NeedType

# デフォルトの増加レート（tick あたり）
DEFAULT_NEED_RATES: Mapping[NeedType, int] = {
    NeedType.HUNGER: 1,   # 100tick で空腹が限界に達する
    NeedType.FATIGUE: 0,  # 疲労は行動 (interact/travel/attack) でのみ増える
                          # — 「何もしなくても 100tick で詰む」構造を解消する
                          # ため自然増加を切る (Y_after_pr634 後続)。
                          # シナリオ側で必要なら rates 引数で上書きできる。
}

DEFAULT_FATIGUE_CRITICAL_THRESHOLD = 95


@dataclass(frozen=True)
class NeedsDecayTick:
    """1 tick 分の欲求増加と限界ダメージの設定。"""

    rates: Mapping[NeedType, int]
    starvation_damage_per_tick: int = 0
    fatigue_critical_damage_per_tick: int = 0
    fatigue_critical_threshold: int = DEFAULT_FATIGUE_CRITICAL_THRESHOLD


@dataclass(frozen=True)
class NeedsDecayTickResult:
    """``apply_needs_decay_tick`` の結果。"""

    changed: bool

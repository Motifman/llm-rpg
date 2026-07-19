"""疲労の自然増加 (passive decay) を行動以外では 0 に固定する (Y_after_pr634 後続)。

Y_after_pr634 trace で観測された構造的詰み:
- ``DEFAULT_NEED_RATES[FATIGUE] = 1`` のため、何もしなくても 100 tick で
  全 player が exhausted (疲労 100) に到達
- survival_island_v2 は 140 tick なので全員が構造的に exhausted を経験する
- 「行動の対価」ではなく「時間が経つだけで詰む」設計になっていた
- 結果として後半 wait spam (loop_guard 6 件中 4 件が wait) が発生

本 PR の方針:
- 疲労は **行動 (interact / travel / attack)** のみで増える
- 自然経過 (=何もしない or speech / wait のような軽い tool) では増えない
- 一方で HUNGER は据え置き (食料探し動機がゲーム性の核なので)
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    DEFAULT_NEED_RATES,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


class TestFatiguePassiveDecayIsZero:
    """疲労は時間経過では増えない。"""

    def test_fatigue_passive_decay_rate_zero(self) -> None:
        """行動以外で疲労が増えると「何もしなくても詰む」構造になるため、
        ``DEFAULT_NEED_RATES[FATIGUE]`` は 0 に固定する。"""
        assert DEFAULT_NEED_RATES[NeedType.FATIGUE] == 0

    def test_value_one_regression_check(self) -> None:
        """Y_after_pr634 で 1 → 0 に下げた。回帰で 1 に戻ると 140 tick の
        survival シナリオで再び全員 exhausted ロックになるので明示的に弾く。"""
        assert DEFAULT_NEED_RATES[NeedType.FATIGUE] < 1


class TestHungerPassiveDecayIsUnchanged:
    """HUNGER は据え置き — 食料探し動機を消さない。"""

    def test_hunger_passive_decay_rate_stays_one(self) -> None:
        """空腹は時間で増える設計を維持する。survival シナリオでは食料探しが
        ゲームの核なので、FATIGUE と一緒に 0 に落とさない。"""
        assert DEFAULT_NEED_RATES[NeedType.HUNGER] == 1

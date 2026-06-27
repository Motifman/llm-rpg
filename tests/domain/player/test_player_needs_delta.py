"""
PR-T: ``PlayerStatusAggregate`` に「前 tick からの need 変化」を計算する
仕組みを追加するテスト。

LLM agent が trajectory (= 改善中 / 悪化中) を能動的に追えるよう、prompt の
「身体の状態」section に「疲労: 高い（68/100、前回 -2）」のような差分を
出すための基盤。

Y 実走の subagent 観察で「疲労 100 で 40 tick 寝続けて回復していないと
LLM が発話し続けた」現象は、実は数値は下がっていたが LLM が trajectory を
認知できなかった silent failure と推測される。これを「変化分の明示表示」で
構造的に解消する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


def _make_player(*, hunger: int = 0, fatigue: int = 0) -> PlayerStatusAggregate:
    """test 用最小の player aggregate を組み立てる。"""
    exp_table = ExpTable(100, 1.5)
    player = PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )
    if hunger:
        player.increase_need(NeedType.HUNGER, hunger)
    if fatigue:
        player.increase_need(NeedType.FATIGUE, fatigue)
    return player


class TestComputeNeedDeltas:
    """``compute_need_deltas()`` は前回 snapshot からの差分を返す。"""

    def test_initial_call_returns_zero_for_all_needs(self):
        """snapshot が無い初期状態では全 need の delta は 0。"""
        player = _make_player(hunger=20, fatigue=30)
        deltas = player.compute_need_deltas()
        assert deltas.get(NeedType.HUNGER, 0) == 0
        assert deltas.get(NeedType.FATIGUE, 0) == 0

    def test_snapshot_then_change_then_delta(self):
        """snapshot 後に need が変化すると、その変化が delta として返る。"""
        player = _make_player(hunger=20, fatigue=30)
        player.snapshot_needs_for_delta()
        # 疲労が +5、空腹が +3 になった
        player.increase_need(NeedType.FATIGUE, 5)
        player.increase_need(NeedType.HUNGER, 3)
        deltas = player.compute_need_deltas()
        assert deltas[NeedType.FATIGUE] == 5
        assert deltas[NeedType.HUNGER] == 3

    def test_negative_delta_means_recovery(self):
        """need が減ったら delta は負値 (= 回復)。"""
        player = _make_player(hunger=60, fatigue=80)
        player.snapshot_needs_for_delta()
        # 疲労が wait などで -10 回復
        player.satisfy_need(NeedType.FATIGUE, 10)
        deltas = player.compute_need_deltas()
        assert deltas[NeedType.FATIGUE] == -10

    def test_snapshot_overwrites_previous_baseline(self):
        """2 回目の snapshot 後の delta は新しい baseline からの差分。"""
        player = _make_player(fatigue=50)
        player.snapshot_needs_for_delta()      # baseline = 50
        player.increase_need(NeedType.FATIGUE, 10)  # 現在 = 60
        player.snapshot_needs_for_delta()      # baseline 更新 = 60
        player.increase_need(NeedType.FATIGUE, 5)   # 現在 = 65
        deltas = player.compute_need_deltas()
        # baseline 60 → 現在 65 なので +5、+15 ではない
        assert deltas[NeedType.FATIGUE] == 5

    def test_compute_does_not_modify_state(self):
        """compute_need_deltas は副作用を持たない (= 何度呼んでも同じ結果)。"""
        player = _make_player(fatigue=50)
        player.snapshot_needs_for_delta()
        player.increase_need(NeedType.FATIGUE, 5)
        d1 = player.compute_need_deltas()
        d2 = player.compute_need_deltas()
        assert d1 == d2


class TestDescribeAllWithDeltas:
    """``AgentNeeds.describe_all_with_deltas`` が delta を末尾に併記する。"""

    def test_no_delta_falls_back_to_describe_all(self):
        """delta が空 dict なら従来の describe と同じ文字列 (= 後方互換)。"""
        player = _make_player(fatigue=50)
        with_delta = player.needs.describe_all_with_deltas({})
        without_delta = player.needs.describe_all()
        assert with_delta == without_delta

    def test_positive_delta_shows_plus_sign(self):
        """+N (= 悪化) は「前回 +N」と併記される。"""
        player = _make_player(fatigue=50)
        player.snapshot_needs_for_delta()
        player.increase_need(NeedType.FATIGUE, 5)
        deltas = player.compute_need_deltas()
        lines = player.needs.describe_all_with_deltas(deltas)
        fatigue_line = next(l for l in lines if "疲労" in l)
        assert "前回 +5" in fatigue_line

    def test_negative_delta_shows_minus_sign(self):
        """-N (= 改善) は「前回 -N」と併記される。"""
        player = _make_player(fatigue=80)
        player.snapshot_needs_for_delta()
        player.satisfy_need(NeedType.FATIGUE, 10)
        deltas = player.compute_need_deltas()
        lines = player.needs.describe_all_with_deltas(deltas)
        fatigue_line = next(l for l in lines if "疲労" in l)
        assert "前回 -10" in fatigue_line

    def test_zero_delta_no_suffix(self):
        """delta=0 のときは「前回」表記なし (= ノイズ削減)。"""
        player = _make_player(fatigue=50)
        player.snapshot_needs_for_delta()
        # 変化なし
        deltas = player.compute_need_deltas()
        lines = player.needs.describe_all_with_deltas(deltas)
        fatigue_line = next(l for l in lines if "疲労" in l)
        assert "前回" not in fatigue_line

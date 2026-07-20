"""HP をプロンプトの「身体の状態」に、値 + 前 turn からの増減つきで出す基盤。

観察 (v3coop_postrefactor_001) で、プレイヤー自身の HP はプロンプトのどこにも
描画されておらず (空腹・疲労のみ)、エージェントは被弾観測を暗算で積み上げて
HP を推定していた。rolling summary で古い被弾観測が圧縮されると累計がズレ、
リオは実 HP ~10 の状況を「被弾累積40」と誤認したまま無自覚にダウンした。

need の trajectory 表示 (`AgentNeed.describe(delta)`) と対称に、HP にも
「HP: 60/100（危険）、前回 -12」の値 + 増減表示を与え、暗算依存を解消する。
HP は need と符号の意味が逆 (+ が回復=良い、- が被弾=悪い) 点に注意。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


def _make_player(*, hp: int = 100, max_hp: int = 100) -> PlayerStatusAggregate:
    """test 用最小の player aggregate を組み立てる。"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(max_hp, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=max_hp),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


class TestComputeHpDelta:
    """``compute_hp_delta()`` は前回 snapshot からの HP 変化を返す。"""

    def test_initial_call_returns_zero(self):
        """snapshot が無い初期状態では delta は 0。"""
        player = _make_player(hp=100)
        assert player.compute_hp_delta() == 0

    def test_snapshot_then_damage_gives_negative_delta(self):
        """snapshot 後に被弾すると delta は負値 (= HP が減った)。"""
        player = _make_player(hp=100)
        player.snapshot_hp_for_delta()
        player.apply_damage(30)
        assert player.compute_hp_delta() == -30

    def test_snapshot_then_heal_gives_positive_delta(self):
        """snapshot 後に回復すると delta は正値 (= HP が増えた)。"""
        player = _make_player(hp=40)
        player.snapshot_hp_for_delta()
        player.heal_hp(20)
        assert player.compute_hp_delta() == 20

    def test_snapshot_overwrites_baseline(self):
        """2 回目の snapshot 後は新しい baseline からの差分になる。"""
        player = _make_player(hp=100)
        player.snapshot_hp_for_delta()
        player.apply_damage(20)          # 80
        player.snapshot_hp_for_delta()   # baseline 更新 = 80
        player.apply_damage(10)          # 70
        assert player.compute_hp_delta() == -10

    def test_compute_has_no_side_effect(self):
        """compute_hp_delta は副作用を持たない (= 何度呼んでも同じ)。"""
        player = _make_player(hp=100)
        player.snapshot_hp_for_delta()
        player.apply_damage(15)
        assert player.compute_hp_delta() == player.compute_hp_delta() == -15


class TestHpDescribe:
    """``Hp.describe(delta)`` が値 + tier + 増減を人間可読で返す。"""

    def test_includes_value_and_max(self):
        """HP の実数値と最大値を含む。"""
        line = Hp(value=60, max_hp=100).describe()
        assert "60/100" in line

    def test_low_hp_is_flagged_dangerous(self):
        """HP が低いと危険域であることが分かる語を含む。"""
        line = Hp(value=15, max_hp=100).describe()
        assert "危険" in line or "瀕死" in line

    def test_negative_delta_shows_damage(self):
        """delta が負 (= 被弾) のとき「前回 -N」を併記する。"""
        line = Hp(value=48, max_hp=100).describe(delta=-12)
        assert "前回 -12" in line

    def test_positive_delta_shows_heal(self):
        """delta が正 (= 回復) のとき「前回 +N」を併記する。"""
        line = Hp(value=60, max_hp=100).describe(delta=20)
        assert "前回 +20" in line

    def test_zero_delta_no_suffix(self):
        """delta=0 / None のときは「前回」表記なし (= ノイズ削減)。"""
        assert "前回" not in Hp(value=60, max_hp=100).describe(delta=0)
        assert "前回" not in Hp(value=60, max_hp=100).describe()

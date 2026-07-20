"""採取源の備蓄プール (stock pool) の遅延再生を計算する純粋関数のテスト。

毎 tick 世界中のプールを更新すると重いため、プールは `(stock, stock_tick)` +
静的な `(capacity, refill_interval)` だけを持ち、アクセス時に経過 tick から
現在値を lazy に算出する。この関数はその中核(副作用なし)。

「一度に取れる量」と「備蓄量」と「再生間隔」を分離するモデル: 備蓄が yield 以上
あれば満額採取でき、使い切ると再生を待つ。再生は refill_interval tick ごとに +1。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.service.stock_pool_regen import (
    compute_stock_regen,
)


class TestComputeStockRegen:
    """compute_stock_regen が経過 tick から現在備蓄を lazy に算出する。"""

    def test_no_elapsed_returns_stock_unchanged(self):
        """now == stock_tick なら備蓄は変わらない。"""
        r = compute_stock_regen(
            stock=3, capacity=6, stock_tick=100, refill_interval=8, now=100
        )
        assert r.effective_stock == 3
        assert r.canonical_tick == 100

    def test_regen_by_whole_intervals(self):
        """refill_interval ごとに +1 再生する。"""
        # 24 tick 経過 / interval 8 → +3
        r = compute_stock_regen(
            stock=1, capacity=6, stock_tick=0, refill_interval=8, now=24
        )
        assert r.effective_stock == 4

    def test_capacity_is_capped(self):
        """再生は capacity で頭打ち。"""
        r = compute_stock_regen(
            stock=5, capacity=6, stock_tick=0, refill_interval=8, now=1000
        )
        assert r.effective_stock == 6

    def test_remainder_is_preserved(self):
        """端数(interval 未満の経過)は canonical_tick に残し、進捗を失わない。"""
        # 20 tick / interval 8 → +2 (16 tick 消費), 端数 4 tick は残す
        r = compute_stock_regen(
            stock=0, capacity=6, stock_tick=0, refill_interval=8, now=20
        )
        assert r.effective_stock == 2
        assert r.canonical_tick == 16  # 0 + 2*8、端数4は now(20)まで残る

    def test_at_capacity_resets_tick_to_now(self):
        """満杯に達したら canonical_tick は now に揃える(端数を無限に溜めない)。"""
        r = compute_stock_regen(
            stock=6, capacity=6, stock_tick=0, refill_interval=8, now=50
        )
        assert r.effective_stock == 6
        assert r.canonical_tick == 50

    def test_zero_refill_interval_means_no_regen(self):
        """refill_interval<=0 は再生なし(静的プール)。"""
        r = compute_stock_regen(
            stock=2, capacity=6, stock_tick=0, refill_interval=0, now=1000
        )
        assert r.effective_stock == 2

    def test_clock_going_back_does_not_lose_stock(self):
        """now < stock_tick(再開/時計逆行)でも備蓄は減らない。"""
        r = compute_stock_regen(
            stock=4, capacity=6, stock_tick=100, refill_interval=8, now=50
        )
        assert r.effective_stock == 4

    def test_input_stock_clamped_to_capacity(self):
        """壊れた入力(stock>capacity)は capacity にクランプ。"""
        r = compute_stock_regen(
            stock=99, capacity=6, stock_tick=0, refill_interval=8, now=0
        )
        assert r.effective_stock == 6

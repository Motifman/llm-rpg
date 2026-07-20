"""採取源の備蓄プール (stock pool) の遅延再生を計算する純粋関数。

毎 tick 世界中のプールを更新すると重い (アイドルなプールも全部回すことになる)
ため、プールは object state に ``(stock, stock_tick)`` と静的な
``(capacity, refill_interval)`` だけを持ち、**アクセス時 (採取 / 表示) にのみ**
経過 tick から現在備蓄を lazy に算出する。この関数がその中核で、副作用は持たない。

再生モデル: ``refill_interval`` tick ごとに +1 個、``capacity`` で頭打ち。
端数 (interval 未満の経過) は ``canonical_tick`` に残して進捗を失わないようにする
(呼び出し側はこの canonical_tick を state に書き戻す)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockRegenResult:
    """lazy 再生の算出結果。

    - ``effective_stock``: 現時点で採取に使える備蓄量。
    - ``canonical_tick``: 呼び出し側が state に書き戻すべき新しい stock_tick。
      端数 (まだ +1 に満たない経過分) を保持するため、必ずしも ``now`` と一致しない。
    """

    effective_stock: int
    canonical_tick: int


def compute_stock_regen(
    *,
    stock: int,
    capacity: int,
    stock_tick: int,
    refill_interval: int,
    now: int,
) -> StockRegenResult:
    """``now`` 時点の備蓄量と、書き戻すべき canonical_tick を返す。

    Args:
        stock: ``stock_tick`` 時点の備蓄量。
        capacity: 備蓄の上限。
        stock_tick: ``stock`` を記録した tick。
        refill_interval: +1 個の再生に要する tick 数。0 以下なら再生しない。
        now: 現在 tick。

    副作用なし。何度呼んでも同じ入力なら同じ結果。
    """
    # 入力の防御的クランプ (壊れた state / 手書きシナリオ対策)。
    # capacity 自体が負なら 0 扱いにしてから stock をクランプする
    # (capacity<0 のまま min すると effective_stock が負値になり得る)。
    capacity = max(0, capacity)
    base = max(0, min(stock, capacity))

    # 再生なし (静的プール) / 時刻が進んでいない / 逆行 (再開・時計巻き戻し) は
    # 備蓄を変えず、canonical_tick も動かさない (備蓄を失わない)。
    if refill_interval <= 0 or now <= stock_tick:
        return StockRegenResult(effective_stock=base, canonical_tick=stock_tick)

    elapsed = now - stock_tick
    regen_units = elapsed // refill_interval
    new_stock = min(capacity, base + regen_units)

    if new_stock >= capacity:
        # 満杯: 端数を無限に溜めないよう基準 tick を now に揃える。
        return StockRegenResult(effective_stock=capacity, canonical_tick=now)

    # 未満: 使い切った whole interval だけ tick を進め、端数 (elapsed %
    # refill_interval) は次回に持ち越す。
    consumed_ticks = regen_units * refill_interval
    return StockRegenResult(
        effective_stock=new_stock,
        canonical_tick=stock_tick + consumed_ticks,
    )

"""belief journal の confidence を再計算するルール関数 (U3b)。

semantic_learning_consolidation_design.md「保存 (ルール): belief journal」節:
``confidence = f(支持件数, 反証件数, 経過時間)``。単調増加の機械値
(``EpisodicSemanticClusterPromotionService`` の旧 ``0.4 + 0.1 * len(eps)``)
を廃止し、支持と反証の両方を汲む形に置き換える。

時間減衰項は今回のスコープでは省略する (将来拡張。経過時間が長いほど
confidence を減衰させたい場合は、``occurred_at`` の分布を引数に足す形で
拡張できる)。
"""

from __future__ import annotations

# 初期値: create 直後 (支持 0 / 反証 0) でも「一応 belief として成立する」
# 程度の確信度を持たせる。0.5 未満にして「まだ弱い」ことを表現する。
BASE_CONFIDENCE = 0.4
# 支持 1 件ごとの加点。反証よりゆるやかに効かせる (S1 のような反復一般化が
# 数件で育つ想定)。
SUPPORT_WEIGHT = 0.1
# 反証 1 件ごとの減点。支持より重く効かせる (「訂正は速く効くべき」という
# S3 の要請)。
CONTRADICT_WEIGHT = 0.15

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0


def compute_belief_confidence(support_count: int, contradict_count: int) -> float:
    """支持件数・反証件数から belief の confidence を [0, 1] で計算する。

    ``support_count`` / ``contradict_count`` に負数を渡すと ``ValueError``。
    """
    if not isinstance(support_count, int) or isinstance(support_count, bool):
        raise TypeError("support_count must be int")
    if not isinstance(contradict_count, int) or isinstance(contradict_count, bool):
        raise TypeError("contradict_count must be int")
    if support_count < 0:
        raise ValueError("support_count must be >= 0")
    if contradict_count < 0:
        raise ValueError("contradict_count must be >= 0")

    raw = (
        BASE_CONFIDENCE
        + SUPPORT_WEIGHT * support_count
        - CONTRADICT_WEIGHT * contradict_count
    )
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, raw))


__all__ = [
    "compute_belief_confidence",
    "BASE_CONFIDENCE",
    "SUPPORT_WEIGHT",
    "CONTRADICT_WEIGHT",
]

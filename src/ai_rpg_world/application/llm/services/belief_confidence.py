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

# P3b: CONFIRMATION (信じて行動して当たった) 由来の支持は、予測が外れて得た
# 学び (PREDICTION_ERROR) より証拠として軽い。通常支持の半分に数える。
CONFIRMATION_SUPPORT_WEIGHT = 0.5

# P10: HEARSAY (伝聞) 由来の支持は、自分の体験より弱い証拠なので通常支持の
# 半分に数える。これは source 種別単位の定数 1 個であり、話者ごとの信頼度
# テーブルではない (設計メモ §4「話者の信頼を数値で管理しない」)。
HEARSAY_SUPPORT_WEIGHT = 0.5


def compute_belief_confidence(
    support_count: int,
    contradict_count: int,
    confirmation_support_count: int = 0,
    hearsay_support_count: int = 0,
) -> float:
    """支持件数・反証件数から belief の confidence を [0, 1] で計算する。

    ``confirmation_support_count`` / ``hearsay_support_count`` はどちらも
    ``support_count`` の内数。CONFIRMATION 由来 (P3b) と HEARSAY 由来 (P10) の
    支持はそれぞれ通常支持の 0.5 倍に軽く数える。両者は source 種別が異なる
    排他的な部分集合なので、合計が ``support_count`` を超えてはならない。
    どちらも既定 0 のとき挙動は導入前と完全一致。

    負数、または ``confirmation_support_count + hearsay_support_count >
    support_count`` は ``ValueError``。
    """
    if not isinstance(support_count, int) or isinstance(support_count, bool):
        raise TypeError("support_count must be int")
    if not isinstance(contradict_count, int) or isinstance(contradict_count, bool):
        raise TypeError("contradict_count must be int")
    if (
        not isinstance(confirmation_support_count, int)
        or isinstance(confirmation_support_count, bool)
    ):
        raise TypeError("confirmation_support_count must be int")
    if (
        not isinstance(hearsay_support_count, int)
        or isinstance(hearsay_support_count, bool)
    ):
        raise TypeError("hearsay_support_count must be int")
    if support_count < 0:
        raise ValueError("support_count must be >= 0")
    if contradict_count < 0:
        raise ValueError("contradict_count must be >= 0")
    if confirmation_support_count < 0:
        raise ValueError("confirmation_support_count must be >= 0")
    if hearsay_support_count < 0:
        raise ValueError("hearsay_support_count must be >= 0")
    if confirmation_support_count + hearsay_support_count > support_count:
        raise ValueError(
            "confirmation_support_count + hearsay_support_count "
            "must be <= support_count"
        )

    # CONFIRMATION / HEARSAY 支持をそれぞれ 0.5 掛けで数えた実効支持件数。
    effective_support = (
        support_count
        - (1.0 - CONFIRMATION_SUPPORT_WEIGHT) * confirmation_support_count
        - (1.0 - HEARSAY_SUPPORT_WEIGHT) * hearsay_support_count
    )
    raw = (
        BASE_CONFIDENCE
        + SUPPORT_WEIGHT * effective_support
        - CONTRADICT_WEIGHT * contradict_count
    )
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, raw))


__all__ = [
    "compute_belief_confidence",
    "BASE_CONFIDENCE",
    "SUPPORT_WEIGHT",
    "CONTRADICT_WEIGHT",
    "CONFIRMATION_SUPPORT_WEIGHT",
    "HEARSAY_SUPPORT_WEIGHT",
]

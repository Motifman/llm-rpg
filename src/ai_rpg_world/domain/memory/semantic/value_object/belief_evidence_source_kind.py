"""BeliefEvidenceSourceKind — 証拠 (``BeliefEvidence``) の発生源 Enum。

U2 (証拠台帳統一設計 §2 / semantic_learning_consolidation_design.md
「中核データ: BeliefEvidence」): 学習の素材を 1 つの型に正規化するにあたり、
将来の後続 PR (U2〜U6) で配線される全種別を最初から enum に予約しておく。

- ``PREDICTION_ERROR``: chunk 主観補完 LLM が ``prediction_error`` を
  非 None で埋めたとき (本 PR U2 で転記を配線する唯一の source)
- ``STRUCTURED_FAILURE``: loop_guard の cross_tick_failure トラッカー
  (U6 で配線予定)
- ``MEMO_DISTILL``: memo_done / memo 容量溢れ (U5 で配線予定)
- ``FAMILIARITY``: 既存クラスタ検出の転用 (U3 で配線予定)
- ``CONFIRMATION``: 学びを信じて行動し当たった (U4 で配線予定)
- ``PENDING_RESOLUTION``: 保留中の予測 (約束) の履行/破棄清算 (U10 で配線予定)
"""

from __future__ import annotations

from enum import Enum


class BeliefEvidenceSourceKind(str, Enum):
    """``BeliefEvidence.source_kind`` に入る発生源の種別。"""

    PREDICTION_ERROR = "prediction_error"
    STRUCTURED_FAILURE = "structured_failure"
    MEMO_DISTILL = "memo_distill"
    FAMILIARITY = "familiarity"
    CONFIRMATION = "confirmation"
    PENDING_RESOLUTION = "pending_resolution"
    # P9 (伝聞): 他者が「世界や人がどうであるか」を語った主張の転記。text は
    # claim、cue は claim の対象 (spot/player)、話者は source_speaker に分離して
    # 保持する (belief_hearsay_design.md §2)。自分の体験より弱い証拠として扱う。
    HEARSAY = "hearsay"


__all__ = ["BeliefEvidenceSourceKind"]

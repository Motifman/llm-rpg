"""Atmosphere バッファのエントリ DTO。

通常の観測フィードとは別に、低優先度・高頻度の周囲情報（環境音、匂い、
背景の体感など）を溜めるための汎用エントリ型。プロンプトには 1 行のサマリで
コンパクトに展開される想定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AtmosphereEntry:
    """Atmosphere バッファの 1 エントリ。

    Attributes:
        category: 分類タグ（例: "ambient_sound" / "smell" / "weather_feel"）。
            プロンプト側でのフィルタや表示分けに使う。
        prose: 短い 1 文の表現。
        occurred_at_tick: 発生 tick。古いエントリの淘汰やスロットル判定に使う。
        source_id: 同一カテゴリ内での重複検出キー（例: ambient_sound_id）。
            None なら重複検出対象外。
    """

    category: str
    prose: str
    occurred_at_tick: int
    source_id: Optional[str] = None

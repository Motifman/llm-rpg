"""クロスドメイン効果の観測可視性。

効果が「行為者だけが知るもの (ACTOR_DIRECT)」「同じスポットの第三者にも
見える (PUBLIC_OBSERVABLE)」「外からは観測できない内部状態 (HIDDEN)」の
どれに該当するかを表す。

- ACTOR_DIRECT は行為者のツール結果に直接サマリとして返される。
  観測ストリームには流さない（行為者は自分の行動の直接効果を二重に
  受け取らない）。
- PUBLIC_OBSERVABLE は同スポットに居る第三者に観測イベントとして配信
  される。行為者は配信先から除外される (`_resolve_at_spot_excluding_actor`)。
- HIDDEN はツール結果にも観測にも露出させない。本人プロンプトの現在状態
  セクションには載るが、第三者からは見えない（毒の進行など内臓的な変化
  を表現するため）。
"""

from __future__ import annotations

from enum import Enum


class EffectVisibility(Enum):
    """クロスドメイン効果が誰に届くかの分類。"""

    ACTOR_DIRECT = "ACTOR_DIRECT"
    """行為者本人のツール結果に直接返す。観測には流さない。"""

    PUBLIC_OBSERVABLE = "PUBLIC_OBSERVABLE"
    """同スポットの第三者に観測として届く。行為者は除外。"""

    HIDDEN = "HIDDEN"
    """誰にも観測されない。本人プロンプトの現在状態にのみ反映。"""

"""シナリオの世界で今見えている場面 (Scene) の説明文を作る (#1630)。"""

from __future__ import annotations

from ai_rpg_world.being.contract import Description

CURRENT_SURROUNDINGS_HEADING = "現在地と周囲"
_NO_CURRENT_STATE = "（情報なし）"


def current_surroundings_description(current_state_text: str) -> Description:
    """場面の先頭に置く説明文。状態が無ければ「（情報なし）」と書く。"""
    return Description(heading=CURRENT_SURROUNDINGS_HEADING, text=current_state_text.strip() or _NO_CURRENT_STATE)

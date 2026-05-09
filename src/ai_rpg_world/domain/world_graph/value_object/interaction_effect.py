from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum


@dataclass(frozen=True)
class InteractionEffect:
    effect_type: InteractionEffectTypeEnum
    parameters: Dict[str, Any]
    # Phase 4-E: 効果の観測可視性。シナリオで明示すれば既定値を上書きする。
    # `None` なら effect_type ごとの既定値 (`_DEFAULT_VISIBILITY`) を使う。
    # parameters dict と分離した first-class 属性にして、将来 `visibility`
    # という名のパラメータを使う effect が出てきても衝突しないようにする。
    visibility: Optional[EffectVisibility] = None

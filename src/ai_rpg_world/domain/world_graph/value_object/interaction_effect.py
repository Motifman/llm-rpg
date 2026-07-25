from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
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
    # 効果の適用先 (対人インタラクション基盤)。既定は行為者本人で、これまでの
    # 挙動と同じ。`visibility` と同じ理由で parameters dict と分離した
    # first-class 属性にする。
    #
    # NOTE: `visibility` と違い `Optional` にしない。「未指定」と「ACTOR を明示」を
    # 区別する必要が無く、None 許容にすると適用側が毎回 None 分岐を書くことに
    # なるため。未知の値は loader が ScenarioLoadError で弾く。
    target: EffectTarget = EffectTarget.ACTOR

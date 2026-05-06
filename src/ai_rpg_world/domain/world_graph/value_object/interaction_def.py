from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect


@dataclass(frozen=True)
class InteractionDef:
    """インタラクションの定義。

    Attributes:
        action_name: 操作名（"submit_code" など）。
        display_label: UI 表示用ラベル。
        preconditions: 全て真でないと実行できない前提条件群（暗黙の AND）。
        effects: 成功時に適用される効果群。
        on_failure_observation: 前提条件が満たされず実行が拒否されたとき、
            同じスポットに居る他プレイヤーへ届ける観測メッセージ。
            アクター本人にはツール結果として `failure_message` が返る。
            None の場合は失敗観測を発行しない。
    """

    action_name: str
    display_label: str
    preconditions: Tuple[InteractionCondition, ...]
    effects: Tuple[InteractionEffect, ...]
    on_failure_observation: Optional[str] = None

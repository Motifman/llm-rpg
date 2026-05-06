"""条件 → passage 状態 を宣言的に紐付ける値オブジェクト。

`ReactivePassageBinding` は「対象接続の passage を、predicate の真偽に応じて
2 状態で自動切り替える」宣言。シナリオ作家は scenario_event を 2 つ書く
代わりに、binding を 1 つ宣言するだけで:

  - predicate=True  → on_true_state へ遷移
  - predicate=False → on_false_state へ遷移

を毎 tick 自動で行わせられる。

協力ギミック #15（役割分担リレーパズル）の典型例:
  - target = 「制御室の先の通路」
  - predicate = PLAYER_AT_SPOT(制御室)
  - on_true_state = "OPEN" (DOOR 系の場合)
  - on_false_state = "LOCKED"

set_connection_passage_state は冪等で、状態が変わらない呼び出しでは
イベントを発火しないので、毎 tick 評価でもスパムにはならない。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotGraphDomainException,
)
from ai_rpg_world.domain.common.exception import ValidationException
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


class ReactivePassageBindingValidationException(
    SpotGraphDomainException, ValidationException
):
    """ReactivePassageBinding のバリデーション例外。"""
    error_code = "WORLD_GRAPH.REACTIVE_PASSAGE_BINDING_VALIDATION"


@dataclass(frozen=True)
class ReactivePassageBinding:
    """predicate の真偽に連動して passage の state を自動切り替える宣言。

    Attributes:
        target_connection_id: 対象接続の ID。
        predicate: 評価する条件ツリー（leaf or 合成）。
        on_true_state: predicate=True のとき遷移する state 名（kind 固有）。
        on_false_state: predicate=False のとき遷移する state 名（kind 固有）。

    `target_connection_id` の passage.kind と互換性のある state 名でないと、
    実行時に PassageValidationException が投げられる（with_state 経由）。
    """

    target_connection_id: ConnectionId
    predicate: ScenarioEventCondition
    on_true_state: str
    on_false_state: str

    def __post_init__(self) -> None:
        if not self.on_true_state:
            raise ReactivePassageBindingValidationException(
                "on_true_state must not be empty"
            )
        if not self.on_false_state:
            raise ReactivePassageBindingValidationException(
                "on_false_state must not be empty"
            )
        if self.on_true_state == self.on_false_state:
            raise ReactivePassageBindingValidationException(
                f"on_true_state and on_false_state must differ "
                f"(both '{self.on_true_state}'); a constant state binding "
                f"has no reactive value"
            )

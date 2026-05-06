"""条件 → SpotObject の状態を宣言的に紐付ける値オブジェクト。

`ReactivePassageBinding` の SpotObject 版。predicate の真偽に応じて
対象オブジェクトの `state` 辞書に on_true_state_updates / on_false_state_updates
をマージする（**部分上書き**）。

対象 object の state 全体を置き換えるのではなく、binding が指定したキーだけを
マージするのは、複数 binding が同じ object の異なるキーを管理できるようにする
ため（例: weather binding が "is_flooded" を、age binding が "rust_level" を
別々に制御）。

応用例:
- #10 経時劣化: predicate=「FLAG_AGE_AT_LEAST(last_used, 100)」 →
  on_true_state_updates={"rust_level": "high"}
- #11 天候連鎖: predicate=「WEATHER_IS(STORM)」 →
  on_true_state_updates={"is_flooded": True}
- #12 資源回復: predicate=「OBJECT_STATE_TICK_AT_LEAST(last_harvest_tick + 20)」 →
  on_true_state_updates={"available": True}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ReactiveObjectStateBindingValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@dataclass(frozen=True)
class ReactiveObjectStateBinding:
    """predicate の真偽に連動して SpotObject の state をマージ更新する宣言。

    Attributes:
        target_object_id: 対象オブジェクトの ID。
        predicate: 評価する条件ツリー（leaf or 合成）。
        on_true_state_updates: predicate=True のときに state にマージする
            キー/値の組（タプルで保持して frozen と共存）。
        on_false_state_updates: predicate=False のときに state にマージする
            キー/値の組。
    """

    target_object_id: SpotObjectId
    predicate: ScenarioEventCondition
    on_true_state_updates: Tuple[Tuple[str, Any], ...]
    on_false_state_updates: Tuple[Tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.on_true_state_updates and not self.on_false_state_updates:
            raise ReactiveObjectStateBindingValidationException(
                "either on_true_state_updates or on_false_state_updates must be non-empty"
            )
        # 同じキーが両方に含まれているか確認（普通は両側に同じキーで対の値を
        # 入れる。片側にしか書かれていないキーは、predicate が True/False に
        # 切り替わったとき「古い値が残る」可能性があり混乱を招く。警告ではなく
        # ハードバリデーションにする）。
        true_keys = {k for k, _ in self.on_true_state_updates}
        false_keys = {k for k, _ in self.on_false_state_updates}
        only_true = true_keys - false_keys
        only_false = false_keys - true_keys
        if only_true:
            raise ReactiveObjectStateBindingValidationException(
                f"keys present only in on_true_state_updates: {sorted(only_true)}; "
                f"specify the same keys in on_false_state_updates to define both sides"
            )
        if only_false:
            raise ReactiveObjectStateBindingValidationException(
                f"keys present only in on_false_state_updates: {sorted(only_false)}; "
                f"specify the same keys in on_true_state_updates to define both sides"
            )

    @property
    def managed_state_keys(self) -> Tuple[str, ...]:
        """この binding が管理する state キー（true/false どちらにもあるキー）。"""
        return tuple(k for k, _ in self.on_true_state_updates)

    def updates_for(self, predicate_value: bool) -> Mapping[str, Any]:
        """評価結果に応じたマージ用 state 辞書を返す。"""
        pairs = self.on_true_state_updates if predicate_value else self.on_false_state_updates
        return {k: v for k, v in pairs}

"""条件 → SpotObject の状態を宣言的に紐付ける値オブジェクト。

`ReactivePassageBinding` の SpotObject 版。predicate の真偽に応じて
対象オブジェクトの `state` 辞書に on_true_state_updates / on_false_state_updates
をマージする（**部分上書き**）。

対象 object の state 全体を置き換えるのではなく、binding が指定したキーだけを
マージするのは、複数 binding が同じ object の異なるキーを管理できるようにする
ため（例: weather binding が "is_flooded" を、age binding が "rust_level" を
別々に制御）。

Phase 2-B 以降、両側のキー集合が同じである必要はない（asymmetric 許容）。
on_true_state_updates にしかないキーは「predicate が True のときだけ書く /
False では touch しない」、on_false_state_updates にしかないキーは
「False のときだけ書く / True では touch しない」と解釈する。
これにより、

- 一方向のみ書きたい lifecycle（例: stoke で smelting → ready
  に推移、ready からは interaction 経由で idle に戻す）
- 複数 binding が同じ object の異なる相位の鍵を独立に管理する

といったパターンが、ダミー値を入れずに表現できる。

応用例:
- #10 経時劣化: predicate=「OBJECT_STATE_TICK_AT_LEAST(last_used, 100)」 →
  on_true_state_updates={"rust_level": "high"}
  on_false_state_updates={"rust_level": "low"}
- #11 天候連鎖: predicate=「WEATHER_IS(STORM)」 →
  on_true_state_updates={"is_flooded": True}
  on_false_state_updates={"is_flooded": False}
- 一方向 lifecycle: predicate=「OBJECT_STATE_TICK_AT_LEAST(...) AND OBJECT_STATE(phase=smelting)」 →
  on_true_state_updates={"phase": "ready"}
  on_false_state_updates=()  # phase は触らない（idle/smelting 維持）
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
        # 各側内のキー重複は禁止（同じ binding 内で同じキーに 2 値を書くのは
        # 作家ミス）。両側で同じキーを持つこと自体は許容する（対称制御）。
        for side_name, pairs in (
            ("on_true_state_updates", self.on_true_state_updates),
            ("on_false_state_updates", self.on_false_state_updates),
        ):
            seen: set[str] = set()
            for k, _ in pairs:
                if k in seen:
                    raise ReactiveObjectStateBindingValidationException(
                        f"duplicate key {k!r} in {side_name}"
                    )
                seen.add(k)
        # Phase 2-A 以前の same-key-set 制約は撤廃。
        # asymmetric な lifecycle 表現（一方向書き換え）を許容するため。
        # 詳細は module docstring 参照。

    @property
    def managed_state_keys(self) -> Tuple[str, ...]:
        """この binding が管理する state キー（true/false 両側の和集合）。

        Phase 2-B 以降、true/false で異なるキーセットを許容するため
        union を返す。順序は on_true 側を先に、その後 on_false にしかない
        キーを続ける。
        """
        true_keys = [k for k, _ in self.on_true_state_updates]
        true_set = set(true_keys)
        only_false = [
            k for k, _ in self.on_false_state_updates if k not in true_set
        ]
        return tuple(true_keys + only_false)

    def updates_for(self, predicate_value: bool) -> Mapping[str, Any]:
        """評価結果に応じたマージ用 state 辞書を返す。"""
        pairs = self.on_true_state_updates if predicate_value else self.on_false_state_updates
        return {k: v for k, v in pairs}

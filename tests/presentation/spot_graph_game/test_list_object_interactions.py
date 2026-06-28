"""``_list_object_interactions`` が ``INTERACTION_ACTION_NOT_FOUND`` のときに
LLM に「利用可能な action_name」を実列挙できることを保証する。

Y_after_issue621 trace の発見:
- LLM が ``action_name='gather'`` を ``波が運んだ漂着物`` (= 実際は
  ``search_debris`` を持つ) に投げて INTERACTION_ACTION_NOT_FOUND を受けた
- 受け取った error message は ``利用可能な操作: (なし)``
- ``search_debris`` が定義されているのに空 list を返していた = **bug**

原因: ``_list_object_interactions(runtime, object_id)`` に ``id_mapper.get_str()``
で変換した str (例: ``"driftwood_pile"``) が渡されており、
``interior.get_object(SpotObjectId)`` は値オブジェクトを期待するので常に None
を返していた。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.value_object.interaction_def import (
    InteractionDef,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
    SpotObjectId,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _list_object_interactions,
)


def _make_interaction(action_name: str) -> InteractionDef:
    return InteractionDef(
        action_name=action_name,
        display_label=action_name,
        preconditions=tuple(),
        effects=tuple(),
    )


def _make_runtime_with_object(
    object_id: int,
    interactions: list[str],
    spot_id: int = 1,
) -> MagicMock:
    """指定 spot に 1 個だけ object を持つ runtime stub を作る。"""
    sid = SpotId(spot_id)
    obj = SpotObject(
        object_id=SpotObjectId(object_id),
        name="dummy",
        description="",
        object_type="OTHER",
        state={},
        interactions=tuple(_make_interaction(a) for a in interactions),
    )
    interior = SpotInterior(
        sub_locations=tuple(),
        objects=(obj,),
        ground_items=tuple(),
        discoverable_items=tuple(),
    )

    graph = MagicMock()
    node = MagicMock()
    node.spot_id = sid
    graph.iter_spot_nodes.return_value = [node]

    runtime = MagicMock()
    runtime._spot_graph_repo.find_graph.return_value = graph
    runtime._spot_interior_repo.find_by_spot_id.side_effect = (
        lambda s: interior if s == sid else None
    )
    return runtime


class TestEnumerationActuallyWorks:
    def test_world_object_id_int_を渡すと_その_object_の_action_name_を_返す(
        self,
    ) -> None:
        """これが今回直すバグの核心。Y_after_issue621 では空 list が返っていた。"""
        runtime = _make_runtime_with_object(
            object_id=42, interactions=["search_debris", "examine"]
        )
        result = _list_object_interactions(runtime, 42)
        assert set(result) == {"search_debris", "examine"}

    def test_interactions_が_空の_object_では_空_list_を_返す(self) -> None:
        """純粋に interactions が無い object はそのまま空 list を返す
        (= LLM 側にも (なし) を伝える)。"""
        runtime = _make_runtime_with_object(object_id=42, interactions=[])
        assert _list_object_interactions(runtime, 42) == []

    def test_未知の_world_object_id_は_空_list_を_返す(self) -> None:
        runtime = _make_runtime_with_object(
            object_id=42, interactions=["gather"]
        )
        assert _list_object_interactions(runtime, 99) == []

    def test_runtime_例外時は_空_list_に_fallback(self) -> None:
        runtime = MagicMock()
        runtime._spot_graph_repo.find_graph.side_effect = RuntimeError(
            "graph broken"
        )
        assert _list_object_interactions(runtime, 42) == []

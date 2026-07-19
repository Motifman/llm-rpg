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
# PR-θ3 (経路統合): _list_object_interactions は
# application/llm/services/executors/interact_helpers.py に移動した。
# 旧 runtime_manager からの import はもう機能しない (削除された)。
from ai_rpg_world.application.llm.services.executors.interact_helpers import (
    list_object_interactions as _list_object_interactions,
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
    def test_returns_world_object_id_int_object_action_name(
        self,
    ) -> None:
        """これが今回直すバグの核心。Y_after_issue621 では空 list が返っていた。"""
        runtime = _make_runtime_with_object(
            object_id=42, interactions=["search_debris", "examine"]
        )
        result = _list_object_interactions(runtime, 42)
        assert set(result) == {"search_debris", "examine"}

    def test_returns_interactions_empty_object_empty_list(self) -> None:
        """純粋に interactions が無い object はそのまま空 list を返す
        (= LLM 側にも (なし) を伝える)。"""
        runtime = _make_runtime_with_object(object_id=42, interactions=[])
        assert _list_object_interactions(runtime, 42) == []

    def test_returns_unknown_world_object_id_empty_list(self) -> None:
        """未知の worldobjectid は空 list を返す。"""
        runtime = _make_runtime_with_object(
            object_id=42, interactions=["gather"]
        )
        assert _list_object_interactions(runtime, 99) == []

    def test_runtime_empty_list_fallback_raises_exception(self) -> None:
        """runtime 例外時は 空 list に fallback。"""
        runtime = MagicMock()
        runtime._spot_graph_repo.find_graph.side_effect = RuntimeError(
            "graph broken"
        )
        assert _list_object_interactions(runtime, 42) == []

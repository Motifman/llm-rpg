from __future__ import annotations

from collections import deque
from typing import FrozenSet, List, Optional, Protocol, Tuple, runtime_checkable

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition


@runtime_checkable
class SpotGraphRoutingView(Protocol):
    """経路探索に必要なグラフの読み取り面"""

    def contains_spot(self, spot_id: SpotId) -> bool: ...

    def neighbor_spot_ids_for_routing(self, spot_id: SpotId) -> List[SpotId]: ...


class SpotGraphNavigationService:
    """スポットグラフ上の経路探索（リポジトリ非依存）"""

    def calculate_route(
        self,
        graph: SpotGraphRoutingView,
        from_spot_id: SpotId,
        to_spot_id: SpotId,
    ) -> List[SpotId]:
        """BFS で最短経路（スポットIDのリスト）。到達不能時は空リスト。"""
        if not graph.contains_spot(from_spot_id) or not graph.contains_spot(to_spot_id):
            return []
        if from_spot_id == to_spot_id:
            return [from_spot_id]

        queue = deque([(from_spot_id, [from_spot_id])])
        visited = {from_spot_id}

        while queue:
            current, path = queue.popleft()
            for neighbor in graph.neighbor_spot_ids_for_routing(current):
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == to_spot_id:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        return []

    def can_pass(
        self,
        connection: SpotConnection,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> Tuple[bool, Optional[str]]:
        """通行条件を評価。通れない場合は理由メッセージを返す。"""
        if not connection.passage.traversable:
            return False, "接続が閉鎖されています"
        for cond in connection.passage_conditions:
            ok, msg = self._evaluate_condition(cond, owned_item_spec_ids, world_flags)
            if not ok:
                return False, msg
        return True, None

    def _evaluate_condition(
        self,
        cond: PassageCondition,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> Tuple[bool, Optional[str]]:
        t = cond.condition_type
        if t == PassageConditionTypeEnum.ALWAYS:
            return True, None
        if t == PassageConditionTypeEnum.ITEM_REQUIRED:
            if cond.item_spec_id is None:
                return False, cond.failure_message or "ITEM_REQUIRED に item_spec_id が設定されていません"
            if cond.item_spec_id not in owned_item_spec_ids:
                return False, cond.failure_message or "必要なアイテムを持っていません"
            return True, None
        if t in (PassageConditionTypeEnum.FLAG_SET, PassageConditionTypeEnum.PUZZLE_SOLVED):
            if not cond.flag_name:
                return False, cond.failure_message or "フラグ名が設定されていません"
            if cond.flag_name not in world_flags:
                return False, cond.failure_message or "条件を満たしていません"
            return True, None
        return False, cond.failure_message or "未対応の通行条件です"

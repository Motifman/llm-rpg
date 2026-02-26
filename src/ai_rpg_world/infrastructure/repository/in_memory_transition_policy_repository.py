"""遷移ポリシーリポジトリのインメモリ実装。"""

from typing import List, Dict, Tuple
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import TransitionCondition


class InMemoryTransitionPolicyRepository(ITransitionPolicyRepository):
    """Dict[(from_spot_id, to_spot_id), List[TransitionCondition]] で保持。"""

    def __init__(self, initial: Dict[Tuple[SpotId, SpotId], List[TransitionCondition]] = None):
        self._policies: Dict[Tuple[SpotId, SpotId], List[TransitionCondition]] = dict(initial or {})

    def get_conditions(self, from_spot_id: SpotId, to_spot_id: SpotId) -> List[TransitionCondition]:
        key = (from_spot_id, to_spot_id)
        return list(self._policies.get(key, []))

    def set_conditions(
        self,
        from_spot_id: SpotId,
        to_spot_id: SpotId,
        conditions: List[TransitionCondition],
    ) -> None:
        """テスト・登録用: 指定の遷移に条件を設定する"""
        self._policies[(from_spot_id, to_spot_id)] = list(conditions)

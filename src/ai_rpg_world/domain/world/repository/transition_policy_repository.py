"""ゲートウェイ遷移条件を (from_spot_id, to_spot_id) で取得するポート"""

from abc import ABC, abstractmethod
from typing import List
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import TransitionCondition


class ITransitionPolicyRepository(ABC):
    """(from_spot_id, to_spot_id) をキーに遷移条件リストを返すポート"""

    @abstractmethod
    def get_conditions(self, from_spot_id: SpotId, to_spot_id: SpotId) -> List[TransitionCondition]:
        """指定の遷移に対する条件リストを返す。条件がなければ空リスト。"""
        pass

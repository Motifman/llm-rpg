"""LLM プレイヤー判定のデフォルト実装（ID 集合ベース）"""

from typing import AbstractSet, Set

from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SetBasedLlmPlayerResolver(ILLMPlayerResolver):
    """指定した PlayerId の集合に含まれるプレイヤーを LLM 制御とみなす実装。"""

    def __init__(self, llm_player_ids: AbstractSet[int]) -> None:
        if not isinstance(llm_player_ids, (set, frozenset)):
            raise TypeError("llm_player_ids must be a set or frozenset")
        for pid in llm_player_ids:
            if not isinstance(pid, int) or pid <= 0:
                raise ValueError("llm_player_ids must contain positive integers only")
        self._ids: Set[int] = set(llm_player_ids)

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return player_id.value in self._ids

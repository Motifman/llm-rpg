"""LLM プレイヤー判定の実装（ID 集合ベース / プロフィールベース）"""

from typing import AbstractSet, Set

from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SetBasedLlmPlayerResolver(ILLMPlayerResolver):
    """指定した PlayerId の集合に含まれるプレイヤーを LLM 制御とみなす実装。
    テストや小規模構成向け。プレイヤー数が多い場合は ProfileBasedLlmPlayerResolver を使用する。
    """

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


class ProfileBasedLlmPlayerResolver(ILLMPlayerResolver):
    """PlayerProfile の control_type に基づいて LLM 制御かどうかを判定する実装。
    プレイヤー数が多くてもプロフィールを 1 件取得するだけで判定できる。
    """

    def __init__(self, player_profile_repository: PlayerProfileRepository) -> None:
        if player_profile_repository is None:
            raise TypeError("player_profile_repository must not be None")
        self._profile_repository = player_profile_repository

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        profile = self._profile_repository.find_by_id(player_id)
        if profile is None:
            return False
        return profile.control_type == ControlType.LLM

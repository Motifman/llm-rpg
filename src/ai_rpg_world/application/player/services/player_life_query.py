"""プレイヤーの生死に関する問いを、同じ状態の真実源から答える。"""

from __future__ import annotations

import logging
from typing import Optional

from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


logger = logging.getLogger(__name__)


class PlayerLifeQuery:
    """手番・観測・投票・身体という別々の問いへ、現行規則で答える。

    ``is_down`` と確定 outcome を一つの「生者 / 死者」へ潰さない。蘇生可能な
    昏倒と ``DEAD`` は現在同じ答えになる問いが多いが、意味は異なるため、
    各メソッドが必要な事実を明示して判断する。
    """

    def __init__(
        self,
        *,
        player_status_repository: Optional[PlayerStatusRepository],
        player_outcome_registry: Optional[PlayerOutcomeRegistry],
    ) -> None:
        self._player_status_repository = player_status_repository
        self._player_outcome_registry = player_outcome_registry

    def can_take_turn(self, player_id: PlayerId) -> bool:
        """LLM 手番を回してよいか。情報取得に失敗した側は従来どおり許可する。"""
        registry = self._player_outcome_registry
        if registry is not None:
            try:
                if registry.get_outcome(player_id).is_resolved:
                    return False
            except Exception:
                logger.warning(
                    "outcome_registry.get_outcome failed for player_id=%s; "
                    "falling back to turn-continue",
                    int(player_id),
                    exc_info=True,
                )
        repository = self._player_status_repository
        if repository is None:
            return True
        try:
            status = repository.find_by_id(player_id)
        except Exception:
            logger.warning(
                "player_status_repo.find_by_id failed for player_id=%s; "
                "falling back to turn-continue",
                int(player_id),
                exc_info=True,
            )
            return True
        return status is None or status.can_act()

    def can_receive_world_observation(self, player_id: PlayerId) -> bool:
        """自分以外の世界観測を届けてよいか。取得失敗時は従来どおり届ける。"""
        repository = self._player_status_repository
        if repository is None:
            return True
        try:
            status = repository.find_by_id(player_id)
        except Exception:
            return True
        if status is None:
            return True
        return getattr(status, "is_down", False) is not True

    def can_vote(self, player_id: PlayerId) -> bool:
        """会議の投票母数へ含めてよいか。確定 outcome 全般ではなく退場だけを見る。"""
        registry = self._player_outcome_registry
        if registry is not None and registry.get_outcome(player_id).is_eliminated:
            return False
        return not self.has_reportable_body(player_id)

    def has_reportable_body(self, player_id: PlayerId) -> bool:
        """通報や倒れている間の被害記録の対象となる身体があるか。"""
        repository = self._player_status_repository
        if repository is None:
            return False
        status = repository.find_by_id(player_id)
        return bool(status is not None and getattr(status, "is_down", False))


__all__ = ["PlayerLifeQuery"]

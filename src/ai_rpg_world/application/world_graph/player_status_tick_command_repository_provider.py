"""player statusを更新するtick command用repository束。"""

from typing import Protocol

from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)


class PlayerStatusTickCommandRepositoryProviderPort(Protocol):
    """player statusだけを更新するtick stageへ最小のrepositoryを公開する。"""

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...


__all__ = ["PlayerStatusTickCommandRepositoryProviderPort"]

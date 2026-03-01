"""注意レベル（観測フィルタ）を変更するアプリケーションサービス"""

import logging
from typing import Callable, Any

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.application.world.contracts.commands import ChangeAttentionLevelCommand
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
)


class AttentionLevelApplicationService:
    """プレイヤーの注意レベルを変更するアプリケーションサービス"""

    def __init__(self, player_status_repository: PlayerStatusRepository) -> None:
        self._player_status_repository = player_status_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], Any], context: dict
    ) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise MovementCommandException(
                str(e), player_id=context.get("player_id")
            )
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def change_attention_level(self, command: ChangeAttentionLevelCommand) -> None:
        """指定プレイヤーの注意レベルを変更する。"""
        self._execute_with_error_handling(
            operation=lambda: self._change_attention_level_impl(command),
            context={
                "action": "change_attention_level",
                "player_id": command.player_id,
            },
        )

    def _change_attention_level_impl(
        self, command: ChangeAttentionLevelCommand
    ) -> None:
        player_id = PlayerId(command.player_id)
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            raise PlayerNotFoundException(command.player_id)
        status.set_attention_level(command.attention_level)
        self._player_status_repository.save(status)

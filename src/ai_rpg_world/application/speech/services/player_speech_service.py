"""プレイヤー間発言のアプリケーションサービス（囁き・発言・シャウト）"""

import logging
from typing import Callable, Any, Optional

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.exception import PlayerDownedException, SpeechValidationException
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.exceptions import (
    SpeechApplicationException,
    SpeechCommandException,
    SpeechSystemErrorException,
    PlayerNotFoundException,
    PlayerLocationNotSetException,
)


class PlayerSpeechApplicationService:
    """
    プレイヤーが誰に・どの方法で発言するかを指定し、発言を実行する。
    同一スポットかつ一定範囲内のプレイヤーに観測として届けるのは観測ハンドラ側で行う。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        event_publisher: EventPublisher,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._event_publisher = event_publisher
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self,
        operation: Callable[[], Any],
        context: dict,
    ) -> Any:
        try:
            return operation()
        except SpeechApplicationException:
            raise
        except (PlayerDownedException, SpeechValidationException) as e:
            raise SpeechCommandException(str(e), **context) from e
        except DomainException as e:
            raise SpeechCommandException(str(e), **context) from e
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise SpeechSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            ) from e

    def speak(self, command: SpeakCommand) -> None:
        """
        発言を実行する。
        発言者の現在地（spot_id, coordinate）をリポジトリから取得し、
        集約で検証・イベント発火後、イベントを発行する。
        """
        self._execute_with_error_handling(
            operation=lambda: self._speak_impl(command),
            context={
                "action": "speak",
                "speaker_player_id": command.speaker_player_id,
                "channel": command.channel.value,
            },
        )

    def _speak_impl(self, command: SpeakCommand) -> None:
        speaker_id = PlayerId(command.speaker_player_id)
        status = self._player_status_repository.find_by_id(speaker_id)
        if status is None:
            raise PlayerNotFoundException(command.speaker_player_id)

        if status.current_spot_id is None or status.current_coordinate is None:
            raise PlayerLocationNotSetException(command.speaker_player_id)

        target_player_id: Optional[PlayerId] = None
        if command.channel == SpeechChannel.WHISPER:
            if command.target_player_id is None:
                raise SpeechCommandException("囁きの場合は宛先プレイヤーを指定してください")
            target_player_id = PlayerId(command.target_player_id)

        status.speak(
            content=command.content,
            channel=command.channel,
            spot_id=status.current_spot_id,
            speaker_coordinate=status.current_coordinate,
            target_player_id=target_player_id,
        )

        events = status.get_events()
        if events:
            self._event_publisher.publish_all(events)
            status.clear_events()

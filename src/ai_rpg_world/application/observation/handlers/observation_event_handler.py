"""
観測用イベントハンドラ。
ドメインイベントを購読し、配信先を解決・観測テキストに変換してコンテキストバッファに追加する。
非同期で実行する（LLM 用のため eventual でよい）。
"""

import logging
from typing import Any, Callable, Optional

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
    IObservationRecipientResolver,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ObservationEventHandler(EventHandler[Any]):
    """
    観測対象のドメインイベントを購読し、
    Resolver → Formatter → Buffer のパイプラインでプレイヤーごとに観測を蓄積する。
    非同期ハンドラとして登録し、別 UoW で実行する。
    """

    def __init__(
        self,
        resolver: IObservationRecipientResolver,
        formatter: IObservationFormatter,
        buffer: IObservationContextBuffer,
        unit_of_work_factory: UnitOfWorkFactory,
        player_status_repository: Optional[Any] = None,
    ) -> None:
        self._resolver = resolver
        self._formatter = formatter
        self._buffer = buffer
        self._unit_of_work_factory = unit_of_work_factory
        self._player_status_repository = player_status_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: Any) -> None:
        try:
            self._execute_in_separate_transaction(
                lambda: self._handle_impl(event),
                context={"handler": "ObservationEventHandler", "event_type": type(event).__name__},
            )
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in ObservationEventHandler: %s",
                e,
                extra={"event_type": type(event).__name__},
            )
            raise SystemErrorException(
                f"Observation handling failed: {e}",
                original_exception=e,
            ) from e

    def _execute_in_separate_transaction(self, operation: Callable[[], None], context: dict) -> None:
        """別トランザクションで操作を実行。SKILL の非同期ハンドラ方針に従う。"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Observation event handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def _get_attention_level(self, player_id: PlayerId) -> AttentionLevel:
        """プレイヤーの注意レベルを取得。リポジトリ未設定時は FULL。"""
        if self._player_status_repository is None:
            return AttentionLevel.FULL
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            return AttentionLevel.FULL
        return status.attention_level

    def _handle_impl(self, event: Any) -> None:
        recipients = self._resolver.resolve(event)
        occurred_at = event.occurred_at
        if occurred_at is None:
            from datetime import datetime
            occurred_at = datetime.now()

        for player_id in recipients:
            attention_level = self._get_attention_level(player_id)
            output = self._formatter.format(event, player_id, attention_level=attention_level)
            if output is not None:
                entry = ObservationEntry(occurred_at=occurred_at, output=output)
                self._buffer.append(player_id, entry)

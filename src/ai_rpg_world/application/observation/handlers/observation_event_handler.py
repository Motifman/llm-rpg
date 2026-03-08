"""
観測用イベントハンドラ。
ドメインイベントを購読し、配信先を解決・観測テキストに変換してコンテキストバッファに追加する。
非同期で実行する（LLM 用のため eventual でよい）。
LLM ターン駆動用に、turn_trigger と llm_player_resolver を渡すと観測を蓄積したあと schedule_turn する。
ゲーム内時刻はハンドラの責務で付与する（game_time_provider と world_time_config を渡すと観測に付与）。
"""

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    ILlmTurnTrigger,
)
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
    game_time_provider と world_time_config を渡すと、観測エントリにゲーム内時刻ラベルを付与する。
    """

    def __init__(
        self,
        resolver: IObservationRecipientResolver,
        formatter: IObservationFormatter,
        buffer: IObservationContextBuffer,
        unit_of_work_factory: UnitOfWorkFactory,
        player_status_repository: Optional[Any] = None,
        turn_trigger: Optional[ILlmTurnTrigger] = None,
        llm_player_resolver: Optional[ILLMPlayerResolver] = None,
        game_time_provider: Optional[Any] = None,
        world_time_config: Optional[Any] = None,
    ) -> None:
        self._resolver = resolver
        self._formatter = formatter
        self._buffer = buffer
        self._unit_of_work_factory = unit_of_work_factory
        self._player_status_repository = player_status_repository
        self._turn_trigger = turn_trigger
        self._llm_player_resolver = llm_player_resolver
        self._game_time_provider = game_time_provider
        self._world_time_config = world_time_config
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

    def _get_game_time_label(self, occurred_tick: Optional[Any] = None) -> Optional[str]:
        """イベント発生時刻に対応するゲーム内時刻ラベルを返す。未設定時は None。"""
        if self._game_time_provider is None or self._world_time_config is None:
            return None
        from ai_rpg_world.domain.world.value_object.game_date_time import (
            game_date_time_from_tick,
        )
        tick = occurred_tick or self._game_time_provider.get_current_tick()
        ticks_per_day = self._world_time_config.get_ticks_per_day()
        days_per_month = self._world_time_config.get_days_per_month()
        months_per_year = self._world_time_config.get_months_per_year()
        game_dt = game_date_time_from_tick(
            tick.value, ticks_per_day, days_per_month, months_per_year
        )
        return game_dt.format_for_display()

    def _handle_impl(self, event: Any) -> None:
        recipients = self._resolver.resolve(event)
        occurred_at = self._resolve_occurred_at(event)
        game_time_label = self._get_game_time_label(getattr(event, "occurred_tick", None))

        for player_id in recipients:
            attention_level = self._get_attention_level(player_id)
            output = self._formatter.format(event, player_id, attention_level=attention_level)
            if output is not None:
                self._append_observation(player_id, output, occurred_at, game_time_label)
                self._maybe_schedule_turn(player_id, output)

    def _resolve_occurred_at(self, event: Any) -> datetime:
        occurred_at = getattr(event, "occurred_at", None)
        if occurred_at is None:
            return datetime.now()
        return occurred_at

    def _append_observation(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
        occurred_at: datetime,
        game_time_label: Optional[str],
    ) -> None:
        entry = ObservationEntry(
            occurred_at=occurred_at,
            output=output,
            game_time_label=game_time_label,
        )
        self._buffer.append(player_id, entry)

    def _maybe_schedule_turn(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
    ) -> None:
        if not output.causes_interrupt:
            return
        if self._turn_trigger is None or self._llm_player_resolver is None:
            return
        if not self._llm_player_resolver.is_llm_controlled(player_id):
            return
        self._turn_trigger.schedule_turn(player_id)

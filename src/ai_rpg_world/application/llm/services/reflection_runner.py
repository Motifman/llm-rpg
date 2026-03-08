"""Reflection の定期実行を担うランナー。

in-game day 境界で ReflectionService を LLM プレイヤー向けに実行する。
重複実行を避けるため、IReflectionStatePort でプレイヤーごとの最終成功 game day と
reflection cursor を記録する。cursor は wall clock ではなく「反映済み境界」の意味。
実行済み state は reflection 成功後にのみ更新し、失敗時は翌 tick 以降に再試行可能。
"""

import logging
from datetime import datetime
from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    IReflectionRunner,
    IReflectionService,
    IReflectionStatePort,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)


# 初回実行時に対象とする cursor（全期間）
_EPOCH_SINCE = datetime.min


class DefaultReflectionRunner(IReflectionRunner):
    """
    in-game day が変わったタイミングで ReflectionService.run を LLM プレイヤー全員に実行する。
    state_port で最終成功 game day と reflection cursor を保持し、1 日に 1 回を超えて成功記録しない。
    失敗時は state_port を更新しないため、翌 tick 以降に再試行される。
    since（reflection cursor）は前回成功境界。同一エピソードの重複反映を防ぐ。
    """

    def __init__(
        self,
        reflection_service: IReflectionService,
        player_status_repository: PlayerStatusRepository,
        llm_player_resolver: ILLMPlayerResolver,
        world_time_config: WorldTimeConfigService,
        state_port: Optional[IReflectionStatePort] = None,
    ) -> None:
        if not isinstance(reflection_service, IReflectionService):
            raise TypeError("reflection_service must be IReflectionService")
        if not isinstance(
            player_status_repository, PlayerStatusRepository
        ):
            raise TypeError(
                "player_status_repository must be PlayerStatusRepository"
            )
        if not isinstance(llm_player_resolver, ILLMPlayerResolver):
            raise TypeError("llm_player_resolver must be ILLMPlayerResolver")
        if not isinstance(world_time_config, WorldTimeConfigService):
            raise TypeError("world_time_config must be WorldTimeConfigService")

        self._reflection_service = reflection_service
        self._player_status_repository = player_status_repository
        self._llm_player_resolver = llm_player_resolver
        self._world_time_config = world_time_config
        if state_port is not None and not isinstance(state_port, IReflectionStatePort):
            raise TypeError("state_port must be IReflectionStatePort or None")
        if state_port is None:
            from ai_rpg_world.application.llm.services.in_memory_reflection_state_port import (
                InMemoryReflectionStatePort,
            )
            state_port = InMemoryReflectionStatePort()
        self._state_port = state_port
        self._logger = logging.getLogger(self.__class__.__name__)

    def run_after_tick(self, current_tick: WorldTick) -> None:
        ticks_per_day = self._world_time_config.get_ticks_per_day()
        if ticks_per_day <= 0:
            return

        current_game_day = current_tick.value // ticks_per_day

        for status in self._player_status_repository.find_all():
            player_id = status.player_id
            if not self._llm_player_resolver.is_llm_controlled(player_id):
                continue

            last_day = self._state_port.get_last_reflection_game_day(player_id)
            if last_day is not None and last_day >= current_game_day:
                continue

            since = self._state_port.get_reflection_cursor(player_id) or _EPOCH_SINCE

            try:
                self._reflection_service.run(
                    player_id,
                    since=since,
                    episode_limit=20,
                )
                # cursor: 反映済み境界。次フェーズで in-game tick/day ベースに差し替え可能
                self._state_port.mark_reflection_success(
                    player_id, current_game_day, datetime.now()
                )
            except Exception as e:
                self._logger.warning(
                    "Reflection failed for player %s: %s",
                    player_id.value,
                    str(e),
                    exc_info=True,
                )

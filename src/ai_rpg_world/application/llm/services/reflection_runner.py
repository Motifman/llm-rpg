"""Reflection の定期実行を担うランナー。

in-game day 境界で ReflectionService を LLM プレイヤー向けに実行する。
重複実行を避けるため、プレイヤーごとの最終実行 game day を記録する。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    IReflectionRunner,
    IReflectionService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)


class DefaultReflectionRunner(IReflectionRunner):
    """
    in-game day が変わったタイミングで ReflectionService.run を LLM プレイヤー全員に実行する。
    プレイヤーごとの最終実行 game day を保持し、1 日に 1 回を超えて実行しない。
    """

    def __init__(
        self,
        reflection_service: IReflectionService,
        player_status_repository: PlayerStatusRepository,
        llm_player_resolver: ILLMPlayerResolver,
        world_time_config: WorldTimeConfigService,
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
        self._last_reflection_game_day: dict[int, int] = {}
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

            last_day = self._last_reflection_game_day.get(player_id.value)
            if last_day is not None and last_day >= current_game_day:
                continue

            self._last_reflection_game_day[player_id.value] = current_game_day
            since = datetime.now() - timedelta(days=1)

            try:
                self._reflection_service.run(
                    player_id,
                    since=since,
                    episode_limit=20,
                )
            except Exception as e:
                self._logger.warning(
                    "Reflection failed for player %s: %s",
                    player_id.value,
                    str(e),
                    exc_info=True,
                )

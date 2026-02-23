"""
MonsterDiedEvent を受けて、倒したモンスターが PREY を倒した場合に飢餓を減少させるハンドラ（Phase 6）
"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository


class MonsterDeathHungerHandler(EventHandler[MonsterDiedEvent]):
    """モンスター死亡イベントで、キラーがモンスターかつ獲物（prey）を倒した場合にそのモンスターの飢餓を減らすハンドラ。飢餓状態は Monster 集約に保持する。"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        unit_of_work: UnitOfWork,
    ):
        self._monster_repository = monster_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDiedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in MonsterDeathHungerHandler: %s", e)
            raise SystemErrorException(
                f"Monster death hunger handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDiedEvent) -> None:
        if event.killer_world_object_id is None:
            return

        killer_monster = self._monster_repository.find_by_world_object_id(event.killer_world_object_id)
        if not killer_monster:
            self._logger.debug(
                "Killer monster not found for world_object_id %s, skipping hunger update",
                event.killer_world_object_id,
            )
            return

        dead_monster = self._monster_repository.find_by_id(event.aggregate_id)
        if not dead_monster:
            self._logger.debug(
                "Dead monster %s not found (expected if already removed), skipping hunger update",
                event.aggregate_id,
            )
            return

        dead_race_value = dead_monster.template.race.value
        prey_races = killer_monster.template.prey_races
        if not prey_races or dead_race_value not in prey_races:
            return

        decrease = killer_monster.template.hunger_decrease_on_prey_kill
        if killer_monster.template.starvation_ticks <= 0 or decrease <= 0:
            return

        killer_monster.record_prey_kill(decrease)
        self._monster_repository.save(killer_monster)
        self._logger.debug(
            "Reduced hunger for killer monster %s (prey %s race=%s)",
            killer_monster.monster_id,
            event.aggregate_id,
            dead_race_value,
        )

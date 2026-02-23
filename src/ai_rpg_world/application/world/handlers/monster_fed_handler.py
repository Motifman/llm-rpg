"""MonsterFedEvent を購読し、採食したモンスターの飢餓を減少させるハンドラ。"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.event.monster_events import MonsterFedEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository


class MonsterFedHandler(EventHandler[MonsterFedEvent]):
    """MonsterFedEvent を受けて Monster.record_feed を実行する。"""

    def __init__(self, monster_repository: MonsterRepository):
        self._monster_repository = monster_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterFedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in MonsterFedHandler: %s", e)
            raise SystemErrorException(
                f"Monster fed handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterFedEvent) -> None:
        monster = self._monster_repository.find_by_world_object_id(event.actor_id)
        if not monster:
            self._logger.debug(
                "Monster not found for world_object_id %s, skipping record_feed",
                event.actor_id,
            )
            return
        decrease = monster.template.hunger_decrease_on_feed
        if monster.template.starvation_ticks <= 0 or decrease <= 0:
            return
        monster.record_feed(decrease)
        self._monster_repository.save(monster)

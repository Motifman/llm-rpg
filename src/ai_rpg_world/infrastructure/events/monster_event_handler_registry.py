"""モンスターの意思決定・行動実行に関するイベントハンドラの登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import (
    MonsterDecidedToMoveHandler,
)
from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import (
    MonsterDecidedToUseSkillHandler,
)
from ai_rpg_world.application.world.handlers.monster_decided_to_interact_handler import (
    MonsterDecidedToInteractHandler,
)
from ai_rpg_world.application.world.handlers.monster_fed_handler import MonsterFedHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDecidedToInteractEvent,
    MonsterFedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class MonsterEventHandlerRegistry:
    """モンスターの意思決定イベント（移動・スキル使用・インタラクション）と採食イベントのハンドラを登録する"""

    def __init__(
        self,
        monster_decided_to_move_handler: MonsterDecidedToMoveHandler,
        monster_decided_to_use_skill_handler: MonsterDecidedToUseSkillHandler,
        monster_decided_to_interact_handler: MonsterDecidedToInteractHandler,
        monster_fed_handler: MonsterFedHandler,
    ):
        self._monster_decided_to_move_handler = monster_decided_to_move_handler
        self._monster_decided_to_use_skill_handler = monster_decided_to_use_skill_handler
        self._monster_decided_to_interact_handler = monster_decided_to_interact_handler
        self._monster_fed_handler = monster_fed_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            MonsterDecidedToMoveEvent,
            self._create_event_handler(self._monster_decided_to_move_handler.handle),
            is_synchronous=True,
        )
        event_publisher.register_handler(
            MonsterDecidedToUseSkillEvent,
            self._create_event_handler(self._monster_decided_to_use_skill_handler.handle),
            is_synchronous=True,
        )
        event_publisher.register_handler(
            MonsterDecidedToInteractEvent,
            self._create_event_handler(self._monster_decided_to_interact_handler.handle),
            is_synchronous=True,
        )
        event_publisher.register_handler(
            MonsterFedEvent,
            self._create_event_handler(self._monster_fed_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)

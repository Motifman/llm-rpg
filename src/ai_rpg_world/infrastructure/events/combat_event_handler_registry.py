from typing import TYPE_CHECKING, List

from ai_rpg_world.application.world.handlers.hit_box_damage_handler import HitBoxDamageHandler
from ai_rpg_world.application.world.handlers.combat_aggro_handler import CombatAggroHandler
from ai_rpg_world.application.world.handlers.monster_death_reward_handler import MonsterDeathRewardHandler
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.common.event_publisher import EventPublisher

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class CombatEventHandlerRegistry:
    """戦闘関連イベントハンドラの登録"""

    def __init__(
        self, 
        hit_box_damage_handler: HitBoxDamageHandler,
        combat_aggro_handler: CombatAggroHandler,
        monster_death_reward_handler: MonsterDeathRewardHandler
    ):
        self._hit_box_damage_handler = hit_box_damage_handler
        self._combat_aggro_handler = combat_aggro_handler
        self._monster_death_reward_handler = monster_death_reward_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        # HitBoxヒット時にダメージ適用とヘイト更新を行う
        event_publisher.register_handler(
            HitBoxHitRecordedEvent,
            self._create_event_handler(self._hit_box_damage_handler.handle),
            is_synchronous=True,
        )
        event_publisher.register_handler(
            HitBoxHitRecordedEvent,
            self._create_event_handler(self._combat_aggro_handler.handle),
            is_synchronous=True,
        )
        
        # モンスター死亡時に報酬を付与する
        event_publisher.register_handler(
            MonsterDiedEvent,
            self._create_event_handler(self._monster_death_reward_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)

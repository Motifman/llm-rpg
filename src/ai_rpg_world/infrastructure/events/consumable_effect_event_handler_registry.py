"""ConsumableUsedEvent のイベントハンドラ登録"""


from ai_rpg_world.application.common.event_delivery import CommandEventHandlerRegistrarPort
from ai_rpg_world.application.world.handlers.consumable_effect_handler import ConsumableEffectHandler
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent


class ConsumableEffectEventHandlerRegistry:
    """ConsumableUsedEvent の同期ハンドラ登録（効果を同一トランザクションで適用）"""

    def __init__(self, consumable_effect_handler: ConsumableEffectHandler):
        self._consumable_effect_handler = consumable_effect_handler

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存のイベント対応を、確定の前後を保って共通基盤へ登録する。"""
        registrar.register_required_before_commit(
            ConsumableUsedEvent, lambda event, _context: self._consumable_effect_handler.handle(event),
        )

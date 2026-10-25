
from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.quest.handlers.quest_progress_handler import (
    ItemAddedToInventoryQuestProgressHandler,
    MonsterDiedQuestProgressHandler,
    PlayerDownedQuestProgressHandler,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent


class QuestEventHandlerRegistry:
    """クエスト関連イベントハンドラの登録"""

    def __init__(
        self,
        monster_died_handler: MonsterDiedQuestProgressHandler,
        player_downed_handler: PlayerDownedQuestProgressHandler,
        item_added_to_inventory_handler: ItemAddedToInventoryQuestProgressHandler,
    ):
        self._monster_died_handler = monster_died_handler
        self._player_downed_handler = player_downed_handler
        self._item_added_to_inventory_handler = item_added_to_inventory_handler

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存の進捗更新を、同じ対応と順序で確定後へ登録する。"""
        registrar.register_after_commit(
            MonsterDiedEvent, self._monster_died_handler.handle,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            PlayerDownedEvent, self._player_downed_handler.handle,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            ItemAddedToInventoryEvent, self._item_added_to_inventory_handler.handle,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )

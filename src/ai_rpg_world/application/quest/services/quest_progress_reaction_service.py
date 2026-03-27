import logging
from typing import Callable

from ai_rpg_world.application.quest.exceptions import QuestRewardGrantException
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    ItemTakenFromChestEvent,
    LocationEnteredEvent,
)
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
)


class QuestProgressReactionService:
    """Quest の進捗更新・完了・報酬付与を扱うアプリケーションサービス。"""

    def __init__(
        self,
        quest_repository: QuestRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
    ) -> None:
        self._quest_repository = quest_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def process_monster_died(self, event: MonsterDiedEvent) -> None:
        if event.killer_player_id is None:
            return

        template_id_value = event.template_id
        if template_id_value is None:
            self._logger.debug(
                "Monster template_id is missing for %s, skipping quest progress",
                event.aggregate_id,
            )
            return

        self._process_accepted_quests(
            acceptor_id=event.killer_player_id,
            advance=lambda quest: quest.advance_objective(
                QuestObjectiveType.KILL_MONSTER,
                template_id_value,
            ),
            completion_log="Quest completed",
        )

    def process_player_downed(self, event: PlayerDownedEvent) -> None:
        if event.killer_player_id is None:
            return

        victim_player_id_value = int(event.aggregate_id)
        self._process_accepted_quests(
            acceptor_id=event.killer_player_id,
            advance=lambda quest: quest.advance_objective(
                QuestObjectiveType.KILL_PLAYER,
                victim_player_id_value,
            ),
            completion_log="Quest completed (KILL_PLAYER)",
        )

    def process_item_taken_from_chest(self, event: ItemTakenFromChestEvent) -> None:
        acceptor_id = PlayerId.create(event.player_id_value)
        spot_id_value = event.spot_id.value
        chest_id_value = event.chest_id.value
        self._process_accepted_quests(
            acceptor_id=acceptor_id,
            advance=lambda quest: quest.advance_objective(
                QuestObjectiveType.TAKE_FROM_CHEST,
                spot_id_value,
                target_id_secondary=chest_id_value,
            ),
            completion_log="Quest completed (TAKE_FROM_CHEST)",
        )

    def process_location_entered(self, event: LocationEnteredEvent) -> None:
        if event.player_id_value is None:
            return

        acceptor_id = PlayerId.create(event.player_id_value)
        spot_id_value = event.spot_id.value
        location_id_value = event.location_id.value

        def advance(quest) -> bool:
            any_advanced = False
            if quest.advance_objective(QuestObjectiveType.REACH_SPOT, spot_id_value):
                any_advanced = True
            if quest.advance_objective(
                QuestObjectiveType.REACH_LOCATION,
                location_id_value,
                target_id_secondary=spot_id_value,
            ):
                any_advanced = True
            return any_advanced

        self._process_accepted_quests(
            acceptor_id=acceptor_id,
            advance=advance,
            completion_log="Quest completed (REACH_SPOT/REACH_LOCATION)",
        )

    def process_gateway_triggered(self, event: GatewayTriggeredEvent) -> None:
        if event.player_id_value is None:
            return

        acceptor_id = PlayerId.create(event.player_id_value)
        target_spot_id_value = event.target_spot_id.value
        spot_id_value = event.spot_id.value

        def advance(quest) -> bool:
            if quest.advance_objective(
                QuestObjectiveType.REACH_SPOT,
                target_spot_id_value,
            ):
                return True
            return quest.advance_objective(
                QuestObjectiveType.REACH_SPOT,
                spot_id_value,
            )

        self._process_accepted_quests(
            acceptor_id=acceptor_id,
            advance=advance,
            completion_log="Quest completed (REACH_SPOT gateway)",
        )

    def process_item_added_to_inventory(self, event: ItemAddedToInventoryEvent) -> None:
        item_spec_id_value = event.item_spec_id_value
        if item_spec_id_value is None:
            self._logger.debug(
                "Item spec payload is missing for %s, skipping OBTAIN_ITEM progress",
                event.item_instance_id,
            )
            return

        self._process_accepted_quests(
            acceptor_id=event.aggregate_id,
            advance=lambda quest: quest.advance_objective(
                QuestObjectiveType.OBTAIN_ITEM,
                item_spec_id_value,
            ),
            completion_log="Quest completed (OBTAIN_ITEM)",
        )

    def process_conversation_ended(self, event: ConversationEndedEvent) -> None:
        self._process_accepted_quests(
            acceptor_id=event.aggregate_id,
            advance=lambda quest: quest.advance_objective(
                QuestObjectiveType.TALK_TO_NPC,
                event.npc_id_value,
            ),
            completion_log="Quest completed (TALK_TO_NPC)",
        )

    def _process_accepted_quests(
        self,
        acceptor_id: PlayerId,
        advance: Callable[[object], bool],
        completion_log: str,
    ) -> None:
        quests = self._quest_repository.find_accepted_quests_by_player(acceptor_id)
        for quest in quests:
            advanced = advance(quest)
            if not advanced:
                continue
            if not quest.is_all_objectives_completed():
                self._quest_repository.save(quest)
                continue
            quest.complete()
            self._grant_reward(quest)
            self._quest_repository.save(quest)
            self._logger.info(
                "%s: quest_id=%s, acceptor=%s",
                completion_log,
                quest.quest_id.value,
                quest.acceptor_player_id,
            )

    def _grant_reward(self, quest) -> None:
        """完了したクエストの報酬を受託者に付与する。"""
        acceptor_id = quest.acceptor_player_id
        quest_id_val = quest.quest_id.value
        acceptor_id_val = acceptor_id.value if acceptor_id else None
        player_status = self._player_status_repository.find_by_id(acceptor_id)
        if not player_status:
            raise QuestRewardGrantException(
                f"報酬付与に失敗しました: 受託者のステータスが見つかりません (acceptor_player_id={acceptor_id})",
                quest_id=quest_id_val,
                acceptor_player_id=acceptor_id_val,
            )
        inventory = self._player_inventory_repository.find_by_id(acceptor_id)
        if not inventory:
            raise QuestRewardGrantException(
                f"報酬付与に失敗しました: 受託者のインベントリが見つかりません (acceptor_player_id={acceptor_id})",
                quest_id=quest_id_val,
                acceptor_player_id=acceptor_id_val,
            )

        if quest.issuer_player_id is not None and (
            quest.reserved_gold > 0 or quest.reserved_item_instance_ids
        ):
            self._grant_reserved_reward(quest, player_status, inventory)
        else:
            self._grant_system_reward(quest, player_status, inventory)

        self._player_status_repository.save(player_status)
        self._player_inventory_repository.save(inventory)

    def _grant_reserved_reward(self, quest, player_status, inventory) -> None:
        """プレイヤー発行クエストの確保済み報酬を受託者に付与する。"""
        if quest.reserved_gold > 0:
            player_status.earn_gold(quest.reserved_gold)
        if not quest.reserved_item_instance_ids:
            return
        issuer_inventory = self._player_inventory_repository.find_by_id(
            quest.issuer_player_id
        )
        if not issuer_inventory:
            raise QuestRewardGrantException(
                f"報酬付与に失敗しました: 発行者のインベントリが見つかりません (issuer_player_id={quest.issuer_player_id})",
                quest_id=quest.quest_id.value,
                acceptor_player_id=quest.acceptor_player_id.value if quest.acceptor_player_id else None,
            )
        for item_id in quest.reserved_item_instance_ids:
            issuer_inventory.remove_reserved_item(item_id)
            item_aggregate = self._item_repository.find_by_id(item_id)
            inventory.acquire_item(
                item_id,
                item_spec_id_value=(
                    item_aggregate.item_spec.item_spec_id.value
                    if item_aggregate is not None
                    else None
                ),
            )
        self._player_inventory_repository.save(issuer_inventory)

    def _grant_system_reward(self, quest, player_status, inventory) -> None:
        """システム発行クエストの報酬（ゴールド・経験値・新規アイテム）を受託者に付与する。"""
        reward = quest.reward
        if reward.gold > 0:
            player_status.earn_gold(reward.gold)
        if reward.exp > 0:
            player_status.gain_exp(reward.exp)
        for item_spec_id, quantity in reward.item_rewards:
            item_spec = self._item_spec_repository.find_by_id(item_spec_id)
            if not item_spec:
                raise QuestRewardGrantException(
                    f"報酬付与に失敗しました: 報酬アイテムの仕様が見つかりません (item_spec_id={item_spec_id.value})",
                    quest_id=quest.quest_id.value,
                    acceptor_player_id=quest.acceptor_player_id.value if quest.acceptor_player_id else None,
                )
            instance_id = self._item_repository.generate_item_instance_id()
            item_aggregate = ItemAggregate.create(
                item_instance_id=instance_id,
                item_spec=item_spec,
                quantity=quantity,
            )
            self._item_repository.save(item_aggregate)
            inventory.acquire_item(
                instance_id,
                item_spec_id_value=item_spec.item_spec_id.value,
            )

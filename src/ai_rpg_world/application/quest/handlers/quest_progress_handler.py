"""
MonsterDiedEvent を受けて、受託中クエストの KILL_MONSTER 目標を進め、
全目標達成時は完了＋報酬付与を行う非同期ハンドラ。
"""
import logging
from typing import Callable, Any

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.quest.exceptions import (
    QuestApplicationException,
    QuestRewardGrantException,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository


class QuestProgressHandler(EventHandler[MonsterDiedEvent]):
    """モンスター死亡イベントで、キラーの受託中クエストの KILL_MONSTER 目標を更新し、完了時は報酬付与するハンドラ（非同期）"""

    def __init__(
        self,
        quest_repository: QuestRepository,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        unit_of_work_factory: UnitOfWorkFactory,
    ):
        self._quest_repository = quest_repository
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDiedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException, QuestApplicationException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in QuestProgressHandler: %s", e
            )
            raise SystemErrorException(
                f"Quest progress handling failed: {e}",
                original_exception=e,
            ) from e

    def _execute_in_separate_transaction(
        self, operation: Callable[[], None], context: dict
    ) -> None:
        """別トランザクションで操作を実行（event-handler-patterns に従う）"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException, QuestApplicationException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Quest progress handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDiedEvent) -> None:
        if event.killer_player_id is None:
            return

        def operation():
            monster = self._monster_repository.find_by_id(event.aggregate_id)
            if monster is None:
                self._logger.debug(
                    "Dead monster %s not found, skipping quest progress",
                    event.aggregate_id,
                )
                return
            template_id_value = monster.template.template_id.value

            quests = self._quest_repository.find_accepted_quests_by_player(
                event.killer_player_id
            )
            for quest in quests:
                advanced = quest.advance_objective(
                    QuestObjectiveType.KILL_MONSTER, template_id_value
                )
                if not advanced:
                    continue
                if not quest.is_all_objectives_completed():
                    self._quest_repository.save(quest)
                    continue
                quest.complete()
                self._grant_reward(quest)
                self._quest_repository.save(quest)
                self._logger.info(
                    "Quest completed: quest_id=%s, acceptor=%s",
                    quest.quest_id.value,
                    quest.acceptor_player_id,
                )

        self._execute_in_separate_transaction(
            operation,
            context={"handler": "quest_progress_monster_died"},
        )

    def _grant_reward(self, quest) -> None:
        """完了したクエストの報酬を受託者に付与する。プレイヤー発行時は確保済み報酬を転送する。
        付与に失敗した場合は QuestRewardGrantException を投げ、イベント再配送によるリトライを促す。
        """
        acceptor_id = quest.acceptor_player_id
        reward = quest.reward
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
            inventory.acquire_item(item_id)
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
            inventory.acquire_item(instance_id)

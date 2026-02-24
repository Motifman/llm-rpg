"""
InMemoryQuestRepository - クエストのインメモリリポジトリ
"""
from typing import List, Optional, Dict

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore


class InMemoryQuestRepository(QuestRepository, InMemoryRepositoryBase):
    """クエストリポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _quests(self) -> Dict[QuestId, QuestAggregate]:
        return self._data_store.quests

    def find_by_id(self, quest_id: QuestId) -> Optional[QuestAggregate]:
        pending = self._get_pending_aggregate(quest_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._quests.get(quest_id))

    def find_by_ids(self, quest_ids: List[QuestId]) -> List[QuestAggregate]:
        return [x for qid in quest_ids for x in [self.find_by_id(qid)] if x is not None]

    def save(self, quest: QuestAggregate) -> QuestAggregate:
        cloned = self._clone(quest)

        def operation():
            self._quests[cloned.quest_id] = cloned
            return cloned

        self._register_aggregate(quest)
        self._register_pending_if_uow(quest.quest_id, quest)
        return self._execute_operation(operation)

    def delete(self, quest_id: QuestId) -> bool:
        def operation():
            if quest_id in self._quests:
                del self._quests[quest_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[QuestAggregate]:
        return [self._clone(q) for q in self._quests.values()]

    def generate_quest_id(self) -> QuestId:
        qid = self._data_store.next_quest_id
        self._data_store.next_quest_id += 1
        return QuestId(qid)

    def find_accepted_quests_by_player(self, player_id: PlayerId) -> List[QuestAggregate]:
        """指定プレイヤーが受託しているクエスト一覧"""
        result = []
        for quest in self._quests.values():
            cloned = self._clone(quest)
            if cloned.status == QuestStatus.ACCEPTED and cloned.acceptor_player_id == player_id:
                result.append(cloned)
        return result

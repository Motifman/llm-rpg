from abc import abstractmethod
from typing import List

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class QuestRepository(Repository[QuestAggregate, QuestId]):
    """クエストリポジトリインターフェース"""

    @abstractmethod
    def generate_quest_id(self) -> QuestId:
        """新規クエストIDを生成"""
        pass

    @abstractmethod
    def find_accepted_quests_by_player(self, player_id: PlayerId) -> List[QuestAggregate]:
        """指定プレイヤーが受託しているクエスト一覧を取得（進捗ハンドラ用）"""
        pass

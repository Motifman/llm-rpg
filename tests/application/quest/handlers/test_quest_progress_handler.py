import pytest
from unittest.mock import Mock

from ai_rpg_world.application.quest.handlers.quest_progress_handler import QuestProgressHandler
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.infrastructure.repository.in_memory_quest_repository import (
    InMemoryQuestRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class TestQuestProgressHandler:
    """QuestProgressHandler（非同期・KILL_MONSTER進捗）のテスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def create_uow(self, data_store):
        def create():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create,
                data_store=data_store,
            )
        return create

    @pytest.fixture
    def uow_factory(self, create_uow):
        factory = Mock()
        factory.create.side_effect = create_uow
        return factory

    @pytest.fixture
    def quest_repository(self, data_store, create_uow):
        uow = create_uow()
        return InMemoryQuestRepository(
            data_store=data_store,
            unit_of_work=uow,
        )

    @pytest.fixture
    def monster_repository(self, data_store):
        """モンスターはモックで template_id のみ返す"""
        repo = Mock()
        monster = Mock()
        monster.template = Mock()
        monster.template.template_id = MonsterTemplateId(101)
        repo.find_by_id = Mock(return_value=monster)
        return repo

    @pytest.fixture
    def player_status_repository(self, data_store):
        return Mock()

    @pytest.fixture
    def player_inventory_repository(self, data_store):
        return Mock()

    @pytest.fixture
    def item_repository(self):
        return Mock()

    @pytest.fixture
    def item_spec_repository(self):
        return Mock()

    @pytest.fixture
    def handler(
        self,
        quest_repository,
        monster_repository,
        player_status_repository,
        player_inventory_repository,
        item_repository,
        item_spec_repository,
        uow_factory,
    ):
        return QuestProgressHandler(
            quest_repository=quest_repository,
            monster_repository=monster_repository,
            player_status_repository=player_status_repository,
            player_inventory_repository=player_inventory_repository,
            item_repository=item_repository,
            item_spec_repository=item_spec_repository,
            unit_of_work_factory=uow_factory,
        )

    def test_handle_skips_when_no_killer(self, handler):
        """killer_player_id が None のとき何もしない"""
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=0,
            exp=10,
            gold=5,
            killer_player_id=None,
        )
        handler.handle(event)
        # 例外なく完了することのみ確認

    def test_handle_skips_when_monster_not_found(
        self, handler, monster_repository
    ):
        """モンスターがリポジトリにないときはスキップ"""
        monster_repository.find_by_id.return_value = None
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(999),
            aggregate_type="MonsterAggregate",
            respawn_tick=0,
            exp=10,
            gold=5,
            killer_player_id=PlayerId(1),
        )
        handler.handle(event)
        monster_repository.find_by_id.assert_called_once()

    def test_handle_advances_objective_when_quest_accepted(
        self, handler, quest_repository, data_store
    ):
        """受託中クエストの KILL_MONSTER 目標が進むこと"""
        quest_id = quest_repository.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100, exp=50)
        scope = QuestScope.public_scope()
        quest = QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
        )
        quest.accept_by(PlayerId(1))
        quest_repository.save(quest)

        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=0,
            exp=10,
            gold=5,
            killer_player_id=PlayerId(1),
        )
        handler.handle(event)

        q = quest_repository.find_by_id(quest_id)
        assert q.objectives[0].current_count == 1
        assert q.status.value == "accepted"

    def test_handle_completes_quest_and_grants_reward_when_all_done(
        self,
        handler,
        quest_repository,
        monster_repository,
        player_status_repository,
        player_inventory_repository,
    ):
        """全目標達成でクエスト完了し報酬付与が行われること（モックで検証）"""
        quest_id = quest_repository.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=1,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100, exp=50)
        scope = QuestScope.public_scope()
        quest = QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
        )
        quest.accept_by(PlayerId(1))
        quest_repository.save(quest)

        mock_status = Mock()
        mock_inventory = Mock()
        player_status_repository.find_by_id.return_value = mock_status
        player_inventory_repository.find_by_id.return_value = mock_inventory

        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=0,
            exp=10,
            gold=5,
            killer_player_id=PlayerId(1),
        )
        handler.handle(event)

        q = quest_repository.find_by_id(quest_id)
        assert q.status.value == "completed"
        assert q.objectives[0].current_count == 1
        mock_status.earn_gold.assert_called_once_with(100)
        mock_status.gain_exp.assert_called_once_with(50)
        player_status_repository.save.assert_called_once()
        player_inventory_repository.save.assert_called_once()

    def test_handle_completes_player_issued_quest_grants_reserved_reward(
        self,
        handler,
        quest_repository,
        monster_repository,
        player_status_repository,
        player_inventory_repository,
    ):
        """プレイヤー発行クエスト完了時は確保済みゴールドを受託者に付与し、経験値は付与しない"""
        from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus

        quest_id = quest_repository.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=1,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=50, exp=0)
        scope = QuestScope.public_scope()
        issuer_id = PlayerId(2)
        acceptor_id = PlayerId(1)
        quest = QuestAggregate(
            quest_id=quest_id,
            status=QuestStatus.ACCEPTED,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=issuer_id,
            guild_id=None,
            acceptor_player_id=acceptor_id,
            reserved_gold=50,
            reserved_item_instance_ids=(),
        )
        quest_repository.save(quest)

        mock_acceptor_status = Mock()
        mock_acceptor_inventory = Mock()
        mock_issuer_inventory = Mock()
        player_status_repository.find_by_id.side_effect = lambda pid: (
            mock_acceptor_status if pid == acceptor_id else None
        )
        player_inventory_repository.find_by_id.side_effect = lambda pid: (
            mock_acceptor_inventory if pid == acceptor_id else mock_issuer_inventory if pid == issuer_id else None
        )

        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=0,
            exp=10,
            gold=5,
            killer_player_id=acceptor_id,
        )
        handler.handle(event)

        q = quest_repository.find_by_id(quest_id)
        assert q.status.value == "completed"
        mock_acceptor_status.earn_gold.assert_called_once_with(50)
        mock_acceptor_status.gain_exp.assert_not_called()
        mock_issuer_inventory.remove_reserved_item.assert_not_called()
        player_status_repository.save.assert_called_once()
        player_inventory_repository.save.assert_called_once()

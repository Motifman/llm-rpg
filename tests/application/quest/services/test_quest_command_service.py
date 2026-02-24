import pytest
from datetime import datetime

from ai_rpg_world.application.quest.services.quest_command_service import QuestCommandService
from ai_rpg_world.application.quest.contracts.commands import (
    IssueQuestCommand,
    AcceptQuestCommand,
    CancelQuestCommand,
)
from ai_rpg_world.application.quest.contracts.dtos import QuestCommandResultDto
from ai_rpg_world.application.quest.exceptions.command.quest_command_exception import (
    QuestCreationException,
    QuestNotFoundForCommandException,
    QuestAccessDeniedException,
)
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus, QuestObjectiveType
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_quest_repository import (
    InMemoryQuestRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class TestQuestCommandService:
    """QuestCommandServiceのテスト"""

    @pytest.fixture
    def setup_service(self):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        data_store = InMemoryDataStore()
        uow = InMemoryUnitOfWork(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        quest_repository = InMemoryQuestRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        service = QuestCommandService(
            quest_repository=quest_repository,
            unit_of_work=uow,
        )
        return service, quest_repository, uow

    def test_issue_quest_success(self, setup_service):
        service, quest_repo, uow = setup_service
        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=100,
            reward_exp=50,
        )
        result = service.issue_quest(command)
        assert result.success is True
        assert "quest_id" in result.data
        quest_id_val = result.data["quest_id"]
        quest = quest_repo.find_by_id(QuestId(quest_id_val))
        assert quest is not None
        assert quest.status == QuestStatus.OPEN
        assert len(quest.objectives) == 1
        assert quest.objectives[0].objective_type == QuestObjectiveType.KILL_MONSTER
        assert quest.objectives[0].target_id == 101
        assert quest.objectives[0].required_count == 2
        assert quest.reward.gold == 100
        assert quest.reward.exp == 50

    def test_issue_quest_invalid_objective_type_raises(self, setup_service):
        service, _, _ = setup_service
        command = IssueQuestCommand(
            objectives=[("invalid_type", 101, 2)],
        )
        with pytest.raises(QuestCreationException):
            service.issue_quest(command)

    def test_accept_quest_success(self, setup_service):
        service, quest_repo, uow = setup_service
        quest_id = quest_repo.generate_quest_id()
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
        quest_repo.save(quest)

        command = AcceptQuestCommand(quest_id=quest_id.value, player_id=1)
        result = service.accept_quest(command)
        assert result.success is True
        q = quest_repo.find_by_id(quest_id)
        assert q.status == QuestStatus.ACCEPTED
        assert q.acceptor_player_id == PlayerId(1)

    def test_accept_quest_not_found_raises(self, setup_service):
        service, _, _ = setup_service
        command = AcceptQuestCommand(quest_id=99999, player_id=1)
        with pytest.raises(QuestNotFoundForCommandException):
            service.accept_quest(command)

    def test_accept_quest_direct_scope_wrong_player_raises(self, setup_service):
        service, quest_repo, uow = setup_service
        quest_id = quest_repo.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100)
        scope = QuestScope.direct_scope(PlayerId(1))
        quest = QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
        )
        quest_repo.save(quest)
        command = AcceptQuestCommand(quest_id=quest_id.value, player_id=2)
        with pytest.raises(QuestAccessDeniedException):
            service.accept_quest(command)

    def test_cancel_quest_success_by_acceptor(self, setup_service):
        service, quest_repo, uow = setup_service
        quest_id = quest_repo.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100)
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
        quest_repo.save(quest)
        command = CancelQuestCommand(quest_id=quest_id.value, player_id=1)
        result = service.cancel_quest(command)
        assert result.success is True
        q = quest_repo.find_by_id(quest_id)
        assert q.status == QuestStatus.CANCELLED

    def test_cancel_quest_success_by_issuer(self, setup_service):
        service, quest_repo, uow = setup_service
        quest_id = quest_repo.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100)
        scope = QuestScope.public_scope()
        issuer_id = PlayerId(1)
        quest = QuestAggregate.issue_quest(
            quest_id=quest_id,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=issuer_id,
            guild_id=None,
        )
        quest_repo.save(quest)
        command = CancelQuestCommand(quest_id=quest_id.value, player_id=1)
        result = service.cancel_quest(command)
        assert result.success is True
        q = quest_repo.find_by_id(quest_id)
        assert q.status == QuestStatus.CANCELLED

    def test_cancel_quest_not_found_raises(self, setup_service):
        service, _, _ = setup_service
        command = CancelQuestCommand(quest_id=99999, player_id=1)
        with pytest.raises(QuestNotFoundForCommandException):
            service.cancel_quest(command)

    def test_cancel_quest_access_denied_raises(self, setup_service):
        service, quest_repo, uow = setup_service
        quest_id = quest_repo.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=2,
                current_count=0,
            ),
        ]
        reward = QuestReward.of(gold=100)
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
        quest_repo.save(quest)
        command = CancelQuestCommand(quest_id=quest_id.value, player_id=2)
        with pytest.raises(QuestAccessDeniedException):
            service.cancel_quest(command)

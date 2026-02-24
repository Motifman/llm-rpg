import pytest
from datetime import datetime
from unittest.mock import Mock

from ai_rpg_world.application.quest.services.quest_command_service import QuestCommandService
from ai_rpg_world.application.quest.contracts.commands import (
    IssueQuestCommand,
    AcceptQuestCommand,
    ApproveQuestCommand,
    CancelQuestCommand,
)
from ai_rpg_world.application.quest.contracts.dtos import QuestCommandResultDto
from ai_rpg_world.application.quest.exceptions.command.quest_command_exception import (
    QuestCreationException,
    QuestNotFoundForCommandException,
    QuestAccessDeniedException,
    QuestCommandException,
)
from ai_rpg_world.application.quest.exceptions.base_exception import (
    QuestSystemErrorException,
)
from ai_rpg_world.domain.quest.exception.quest_exception import (
    InvalidQuestStatusException,
)
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus, QuestObjectiveType
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.infrastructure.repository.in_memory_quest_repository import (
    InMemoryQuestRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus


def _create_player_status(player_id: PlayerId, gold_amount: int = 0) -> PlayerStatusAggregate:
    """テスト用の PlayerStatus を作成（ゴールド指定可）"""
    base_stats = BaseStats(
        max_hp=100,
        max_mp=100,
        attack=10,
        defense=10,
        speed=10,
        critical_rate=0.0,
        evasion_rate=0.0,
    )
    return PlayerStatusAggregate(
        player_id=player_id,
        base_stats=base_stats,
        stat_growth_factor=StatGrowthFactor.for_level(1),
        exp_table=ExpTable(100, 2.0),
        growth=Growth(1, 0, ExpTable(100, 2.0)),
        gold=Gold.create(gold_amount),
        hp=Hp.create(100, 100),
        mp=Mp.create(100, 100),
        stamina=Stamina.create(100, 100),
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
        guild_repository = InMemoryGuildRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        service = QuestCommandService(
            quest_repository=quest_repository,
            unit_of_work=uow,
            guild_repository=guild_repository,
        )
        return service, quest_repository, uow

    @pytest.fixture
    def setup_service_with_guild(self):
        """Quest + Guild リポジトリ付き（ギルド掲示・承認・受託テスト用）"""
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
        guild_repository = InMemoryGuildRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        service = QuestCommandService(
            quest_repository=quest_repository,
            unit_of_work=uow,
            guild_repository=guild_repository,
        )
        return service, quest_repository, guild_repository, uow

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

    def test_issue_quest_empty_objectives_raises(self, setup_service):
        """目標が空のとき QuestCreationException"""
        service, _, _ = setup_service
        command = IssueQuestCommand(objectives=[], reward_gold=0, reward_exp=0)
        with pytest.raises(QuestCreationException) as exc_info:
            service.issue_quest(command)
        assert "目標" in str(exc_info.value)

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

    def test_cancel_quest_when_completed_raises_quest_command_exception(
        self, setup_service
    ):
        """完了済みクエストをキャンセルすると DomainException が QuestCommandException にラップされる"""
        service, quest_repo, _ = setup_service
        quest_id = quest_repo.generate_quest_id()
        objectives = [
            QuestObjective(
                objective_type=QuestObjectiveType.KILL_MONSTER,
                target_id=101,
                required_count=1,
                current_count=1,
            ),
        ]
        reward = QuestReward.of(gold=100)
        scope = QuestScope.public_scope()
        acceptor_id = PlayerId(1)
        quest = QuestAggregate(
            quest_id=quest_id,
            status=QuestStatus.ACCEPTED,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=None,
            guild_id=None,
            acceptor_player_id=acceptor_id,
            reserved_gold=0,
            reserved_item_instance_ids=(),
        )
        quest.complete()
        quest_repo.save(quest)
        command = CancelQuestCommand(quest_id=quest_id.value, player_id=1)
        with pytest.raises(QuestCommandException) as exc_info:
            service.cancel_quest(command)
        assert exc_info.value.__cause__ is not None
        assert isinstance(
            exc_info.value.__cause__, InvalidQuestStatusException
        )

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

    def test_accept_quest_unexpected_exception_wrapped_as_quest_system_error(
        self, setup_service
    ):
        """リポジトリ等が想定外の例外を投げたとき QuestSystemErrorException にラップされる"""
        service, quest_repo, uow = setup_service
        original_error = RuntimeError("database connection failed")
        quest_repo.find_by_id = Mock(side_effect=original_error)
        command = AcceptQuestCommand(quest_id=1, player_id=1)
        with pytest.raises(QuestSystemErrorException) as exc_info:
            service.accept_quest(command)
        assert exc_info.value.original_exception is original_error

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

    # --- Phase 2: プレイヤー発行・報酬予約 ---

    @pytest.fixture
    def setup_service_with_player_repos(self):
        """PlayerStatus / Inventory / Item リポジトリ付きのサービス（プレイヤー発行テスト用）"""
        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow,
                data_store=data_store,
            )

        data_store = InMemoryDataStore()
        uow = InMemoryUnitOfWork(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        quest_repository = InMemoryQuestRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        player_status_repository = InMemoryPlayerStatusRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        player_inventory_repository = InMemoryPlayerInventoryRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        item_repository = InMemoryItemRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        service = QuestCommandService(
            quest_repository=quest_repository,
            unit_of_work=uow,
            player_status_repository=player_status_repository,
            player_inventory_repository=player_inventory_repository,
            item_repository=item_repository,
        )
        return {
            "service": service,
            "quest_repo": quest_repository,
            "status_repo": player_status_repository,
            "inventory_repo": player_inventory_repository,
            "item_repo": item_repository,
            "uow": uow,
        }

    def test_issue_quest_player_issued_gold_success(self, setup_service_with_player_repos):
        """プレイヤー発行クエスト（ゴールド報酬のみ）が正常に発行され、確保済みゴールドが記録される"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=200))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(issuer_id))

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=100,
            reward_exp=0,
            issuer_player_id=1,
        )
        result = s["service"].issue_quest(command)
        assert result.success is True
        quest_id_val = result.data["quest_id"]
        quest = s["quest_repo"].find_by_id(QuestId(quest_id_val))
        assert quest.issuer_player_id == issuer_id
        assert quest.reserved_gold == 100
        assert quest.reserved_item_instance_ids == ()

        updated_status = s["status_repo"].find_by_id(issuer_id)
        assert updated_status.gold.value == 100

    def test_issue_quest_player_issued_exp_raises(self, setup_service_with_player_repos):
        """プレイヤー発行クエストで経験値報酬を指定すると QuestCreationException"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=200))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(issuer_id))

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            issuer_player_id=1,
        )
        with pytest.raises(QuestCreationException) as exc_info:
            s["service"].issue_quest(command)
        assert "経験値報酬" in str(exc_info.value)

    def test_issue_quest_player_issued_insufficient_gold_raises(
        self, setup_service_with_player_repos
    ):
        """プレイヤー発行クエストでゴールド不足のとき QuestCreationException"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=50))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(issuer_id))

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=100,
            reward_exp=0,
            issuer_player_id=1,
        )
        with pytest.raises(QuestCreationException) as exc_info:
            s["service"].issue_quest(command)
        assert "ゴールド" in str(exc_info.value)

    def test_issue_quest_player_issued_issuer_not_found_raises(
        self, setup_service_with_player_repos
    ):
        """発行者が存在しないとき QuestCreationException"""
        s = setup_service_with_player_repos
        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=100,
            issuer_player_id=999,
        )
        with pytest.raises(QuestCreationException) as exc_info:
            s["service"].issue_quest(command)
        assert "発行者" in str(exc_info.value)

    def test_issue_quest_player_issued_with_items_success(
        self, setup_service_with_player_repos
    ):
        """プレイヤー発行クエスト（アイテム報酬）が正常に発行され、予約アイテムが記録される"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=100))
        inventory = PlayerInventoryAggregate.create_new_inventory(issuer_id)

        item_spec = ItemSpec(
            item_spec_id=ItemSpecId(201),
            name="テスト報酬アイテム",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="報酬用",
            max_stack_size=MaxStackSize(64),
        )
        instance_id = s["item_repo"].generate_item_instance_id()
        item_aggregate = ItemAggregate.create(
            item_instance_id=instance_id,
            item_spec=item_spec,
            quantity=2,
        )
        s["item_repo"].save(item_aggregate)
        inventory.acquire_item(instance_id)
        s["inventory_repo"].save(inventory)

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=0,
            reward_items=[(201, 1)],
            issuer_player_id=1,
        )
        result = s["service"].issue_quest(command)
        assert result.success is True
        quest = s["quest_repo"].find_by_id(QuestId(result.data["quest_id"]))
        assert quest.issuer_player_id == issuer_id
        assert quest.reserved_gold == 0
        assert len(quest.reserved_item_instance_ids) == 1
        assert quest.reserved_item_instance_ids[0] == instance_id

    def test_issue_quest_player_issued_insufficient_items_raises(
        self, setup_service_with_player_repos
    ):
        """プレイヤー発行クエストで報酬アイテムが不足しているとき QuestCreationException"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=100))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(issuer_id))

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=0,
            reward_items=[(999, 1)],
            issuer_player_id=1,
        )
        with pytest.raises(QuestCreationException) as exc_info:
            s["service"].issue_quest(command)
        assert "報酬アイテム" in str(exc_info.value)

    def test_cancel_quest_player_issued_returns_gold_to_issuer(
        self, setup_service_with_player_repos
    ):
        """プレイヤー発行クエストをキャンセルすると確保済みゴールドが発行者に返却される"""
        s = setup_service_with_player_repos
        issuer_id = PlayerId(1)
        s["status_repo"].save(_create_player_status(issuer_id, gold_amount=200))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(issuer_id))

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=100,
            reward_exp=0,
            issuer_player_id=1,
        )
        issue_result = s["service"].issue_quest(command)
        quest_id_val = issue_result.data["quest_id"]

        cancel_command = CancelQuestCommand(quest_id=quest_id_val, player_id=1)
        result = s["service"].cancel_quest(cancel_command)
        assert result.success is True

        updated_status = s["status_repo"].find_by_id(issuer_id)
        assert updated_status.gold.value == 200

    # --- Phase 3: ギルド掲示・承認・受託 ---

    def test_issue_quest_with_guild_id_sets_pending_approval(self, setup_service_with_guild):
        """guild_id を指定して発行すると status=PENDING_APPROVAL になる"""
        service, quest_repo, guild_repo, _ = setup_service_with_guild
        from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        guild_id = guild_repo.generate_guild_id()
        guild = GuildAggregate.create_guild(
            guild_id=guild_id,
            name="G",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild_repo.save(guild)

        command = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            guild_id=guild_id.value,
        )
        result = service.issue_quest(command)
        assert result.success is True
        quest_id_val = result.data["quest_id"]
        quest = quest_repo.find_by_id(QuestId(quest_id_val))
        assert quest.status == QuestStatus.PENDING_APPROVAL
        assert quest.guild_id == guild_id.value
        assert quest.scope.is_guild() is True

    def test_approve_quest_success(self, setup_service_with_guild):
        """オフィサー以上が承認すると status=OPEN になる"""
        service, quest_repo, guild_repo, _ = setup_service_with_guild
        from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
        guild_id = guild_repo.generate_guild_id()
        guild = GuildAggregate.create_guild(
            guild_id=guild_id,
            name="G",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild_repo.save(guild)

        issue_cmd = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            guild_id=guild_id.value,
        )
        issue_result = service.issue_quest(issue_cmd)
        quest_id_val = issue_result.data["quest_id"]

        approve_cmd = ApproveQuestCommand(
            quest_id=quest_id_val,
            approver_player_id=1,
        )
        result = service.approve_quest(approve_cmd)
        assert result.success is True
        quest = quest_repo.find_by_id(QuestId(quest_id_val))
        assert quest.status == QuestStatus.OPEN

    def test_approve_quest_not_officer_raises(self, setup_service_with_guild):
        """MEMBER は承認権限がない"""
        service, quest_repo, guild_repo, _ = setup_service_with_guild
        from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
        guild_id = guild_repo.generate_guild_id()
        guild = GuildAggregate.create_guild(
            guild_id=guild_id,
            name="G",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(inviter_player_id=PlayerId(1), new_player_id=PlayerId(2))
        guild_repo.save(guild)

        issue_cmd = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            guild_id=guild_id.value,
        )
        issue_result = service.issue_quest(issue_cmd)
        quest_id_val = issue_result.data["quest_id"]

        approve_cmd = ApproveQuestCommand(
            quest_id=quest_id_val,
            approver_player_id=2,
        )
        with pytest.raises(QuestAccessDeniedException):
            service.approve_quest(approve_cmd)

    def test_accept_quest_guild_scope_member_success(self, setup_service_with_guild):
        """ギルドスコープのクエストはギルドメンバーが受託可能"""
        service, quest_repo, guild_repo, _ = setup_service_with_guild
        from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
        guild_id = guild_repo.generate_guild_id()
        guild = GuildAggregate.create_guild(
            guild_id=guild_id,
            name="G",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(inviter_player_id=PlayerId(1), new_player_id=PlayerId(2))
        guild_repo.save(guild)

        issue_cmd = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            guild_id=guild_id.value,
        )
        issue_result = service.issue_quest(issue_cmd)
        quest_id_val = issue_result.data["quest_id"]
        service.approve_quest(ApproveQuestCommand(quest_id=quest_id_val, approver_player_id=1))

        accept_cmd = AcceptQuestCommand(quest_id=quest_id_val, player_id=2)
        result = service.accept_quest(accept_cmd)
        assert result.success is True
        q = quest_repo.find_by_id(QuestId(quest_id_val))
        assert q.status == QuestStatus.ACCEPTED
        assert q.acceptor_player_id == PlayerId(2)

    def test_accept_quest_guild_scope_non_member_raises(self, setup_service_with_guild):
        """ギルドスコープのクエストは非メンバーは受託できない"""
        service, quest_repo, guild_repo, _ = setup_service_with_guild
        from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
        guild_id = guild_repo.generate_guild_id()
        guild = GuildAggregate.create_guild(
            guild_id=guild_id,
            name="G",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild_repo.save(guild)

        issue_cmd = IssueQuestCommand(
            objectives=[("kill_monster", 101, 2)],
            reward_gold=0,
            reward_exp=50,
            guild_id=guild_id.value,
        )
        issue_result = service.issue_quest(issue_cmd)
        quest_id_val = issue_result.data["quest_id"]
        service.approve_quest(ApproveQuestCommand(quest_id=quest_id_val, approver_player_id=1))

        accept_cmd = AcceptQuestCommand(quest_id=quest_id_val, player_id=99)
        with pytest.raises(QuestAccessDeniedException):
            service.accept_quest(accept_cmd)

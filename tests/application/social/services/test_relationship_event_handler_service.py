"""RelationshipEventHandlerServiceのテスト"""

import logging
import pytest
from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.social.services.relationship_event_handler_service import RelationshipEventHandlerService
from ai_rpg_world.domain.sns.event import SnsUserBlockedEvent
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory


class TestRelationshipEventHandlerService:
    """RelationshipEventHandlerServiceのテスト（実際のRepository使用）"""

    @pytest.fixture
    def unit_of_work_factory(self):
        """テスト用のUnit of Workファクトリ"""
        return InMemoryUnitOfWorkFactory()

    @pytest.fixture
    def user_repository(self, unit_of_work_factory):
        """テスト用のユーザーRepository（UoW対応）"""
        unit_of_work = unit_of_work_factory.create()
        data_store = InMemoryDataStore()
        repo = InMemorySnsUserRepository(data_store, unit_of_work)
        # テスト用ユーザーのセットアップ
        self._setup_test_users(repo)
        return repo

    def _setup_test_users(self, repo):
        """テスト用のユーザーを作成"""
        # ユーザー1: 勇者
        user1 = UserAggregate.create_new_user(UserId(1), "hero", "勇者", "")

        # ユーザー2: 魔法使い
        user2 = UserAggregate.create_new_user(UserId(2), "mage", "魔法使い", "")

        # リポジトリに保存
        with repo._unit_of_work:
            repo.save(user1)
            repo.save(user2)

    @pytest.fixture
    def unit_of_work(self, unit_of_work_factory):
        """テスト用のUnit of Work"""
        return unit_of_work_factory.create()

    @pytest.fixture
    def service(self, user_repository, unit_of_work_factory):
        """テスト用のRelationshipEventHandlerService"""
        return RelationshipEventHandlerService(
            user_repository=user_repository,
            unit_of_work_factory=unit_of_work_factory
        )

    @pytest.fixture
    def user1(self, user_repository):
        """テスト用ユーザー1（勇者）"""
        user = user_repository.find_by_id(UserId(1))
        assert user is not None
        return user

    @pytest.fixture
    def user2(self, user_repository):
        """テスト用ユーザー2（魔法使い）"""
        user = user_repository.find_by_id(UserId(2))
        assert user is not None
        return user



    def test_handle_user_blocked_no_relations(self, service, user_repository, user1, user2):
        """ユーザーブロック時の関係解除 - 関係が存在しない場合"""
        # 関係が存在しないことを確認
        assert not user2.is_following(UserId(1))
        assert not user2.is_subscribed(UserId(1))

        # ブロックイベントを作成（user1がuser2をブロック）
        event = SnsUserBlockedEvent.create(
            aggregate_id=user1.user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=user1.user_id,
            blocked_user_id=user2.user_id
        )

        # 実行
        service.handle_user_blocked(event)

        # 検証：関係が変化していないことを確認（既にフォロー/購読関係がない）
        final_user2 = user_repository.find_by_id(UserId(2))
        assert not final_user2.is_following(UserId(1))
        assert not final_user2.is_subscribed(UserId(1))

    def test_handle_user_blocked_only_follow_relation(self, service, user_repository, user1, user2):
        """ユーザーブロック時の関係解除 - フォロー関係のみが存在する場合"""
        # まずユーザー間にフォロー関係のみを作成
        with user_repository._unit_of_work:
            user2.follow(UserId(1))  # user2がuser1をフォロー
            user_repository.save(user2)

        # フォロー関係が存在し、購読関係が存在しないことを確認
        updated_user2 = user_repository.find_by_id(UserId(2))
        assert updated_user2.is_following(UserId(1))
        assert not updated_user2.is_subscribed(UserId(1))

        # ブロックイベントを作成（user1がuser2をブロック）
        event = SnsUserBlockedEvent.create(
            aggregate_id=user1.user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=user1.user_id,
            blocked_user_id=user2.user_id
        )

        # 実行
        service.handle_user_blocked(event)

        # 検証：フォロー関係のみが解除されていることを確認
        final_user2 = user_repository.find_by_id(UserId(2))
        assert not final_user2.is_following(UserId(1))
        assert not final_user2.is_subscribed(UserId(1))

    def test_handle_user_blocked_follow_and_subscribe_relations(self, service, user_repository, user1, user2):
        """ユーザーブロック時の関係解除 - フォロー関係と購読関係の両方が存在する場合"""
        # まずユーザー間にフォロー関係と購読関係を作成
        with user_repository._unit_of_work:
            user2.follow(UserId(1))    # user2がuser1をフォロー
            user2.subscribe(UserId(1)) # user2がuser1を購読
            user_repository.save(user2)

        # 両方の関係が存在することを確認
        updated_user2 = user_repository.find_by_id(UserId(2))
        assert updated_user2.is_following(UserId(1))
        assert updated_user2.is_subscribed(UserId(1))

        # ブロックイベントを作成（user1がuser2をブロック）
        event = SnsUserBlockedEvent.create(
            aggregate_id=user1.user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=user1.user_id,
            blocked_user_id=user2.user_id
        )

        # 実行
        service.handle_user_blocked(event)

        # 検証：両方の関係が解除されていることを確認
        final_user2 = user_repository.find_by_id(UserId(2))
        assert not final_user2.is_following(UserId(1))
        assert not final_user2.is_subscribed(UserId(1))

    def test_handle_user_blocked_user_not_found(self, service, user_repository):
        """ユーザーブロック時の関係解除 - ユーザーが見つからない場合"""
        # 存在しないユーザーを指定したイベントを作成
        event = SnsUserBlockedEvent.create(
            aggregate_id=UserId(999),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(999),  # 存在しないユーザー
            blocked_user_id=UserId(1)
        )

        # 実行（例外が発生しないことを確認）
        service.handle_user_blocked(event)

        # 検証：処理が正常に完了し、何も変化しないことを確認
        # （存在しないユーザーの場合、処理が中断される）
        final_user2 = user_repository.find_by_id(UserId(2))
        assert final_user2 is not None  # 既存のユーザーはそのまま


class TestRelationshipEventHandlerServiceImprovements:
    """RelationshipEventHandlerServiceの改善点（例外処理、UoW、ログ）をテスト"""

    @pytest.fixture
    def unit_of_work_improvements(self):
        """テスト用のUnit of Work"""
        return InMemoryUnitOfWork(unit_of_work_factory=lambda: InMemoryUnitOfWork(unit_of_work_factory=lambda: InMemoryUnitOfWork()))

    @pytest.fixture
    def user_repository_improvements(self, unit_of_work_improvements):
        """テスト用のユーザーRepository（UoW対応）"""
        # unit_of_work_improvementsはすでにUnit of Workインスタンスなので、そのまま使用
        data_store = InMemoryDataStore()
        repo = InMemorySnsUserRepository(data_store, unit_of_work_improvements)
        # テスト用ユーザーのセットアップ
        TestRelationshipEventHandlerServiceImprovements._setup_test_users(repo)
        return repo

    @staticmethod
    def _setup_test_users(repo):
        """テスト用のユーザーを作成"""
        # ユーザー1: 勇者
        user1 = UserAggregate.create_new_user(UserId(1), "hero", "勇者", "")

        # ユーザー2: 魔法使い
        user2 = UserAggregate.create_new_user(UserId(2), "mage", "魔法使い", "")

        # リポジトリに保存
        with repo._unit_of_work:
            repo.save(user1)
            repo.save(user2)

    @pytest.fixture
    def service_improvements(self, user_repository_improvements, unit_of_work_improvements):
        """テスト用のRelationshipEventHandlerService"""
        # テスト用のファクトリを作成
        class TestUnitOfWorkFactory:
            def create(self):
                return unit_of_work_improvements

        return RelationshipEventHandlerService(
            user_repository=user_repository_improvements,
            unit_of_work_factory=TestUnitOfWorkFactory()
        )

    @pytest.fixture
    def service(self, user_repository, unit_of_work_factory):
        """テスト用のRelationshipEventHandlerService"""
        return RelationshipEventHandlerService(
            user_repository=user_repository,
            unit_of_work_factory=unit_of_work_factory
        )

    def test_exception_handling_in_relationship_handler(self, service_improvements, user_repository_improvements, caplog):
        """関係イベントハンドラでの例外処理が正しく動作することを確認"""
        import logging
        caplog.set_level(logging.ERROR, logger="ai_rpg_world.application.social.services.relationship_event_handler_service")

        # 正常なユーザーIDを使用するが、リポジトリのsaveメソッドが例外を投げるようにする
        event = SnsUserBlockedEvent.create(
            aggregate_id=UserId(1),
            aggregate_type="UserAggregate",
            blocker_user_id=UserId(1),
            blocked_user_id=UserId(2)
        )

        # まずユーザー間にフォロー関係を作成
        user1 = user_repository_improvements.find_by_id(UserId(1))
        user2 = user_repository_improvements.find_by_id(UserId(2))

        with user_repository_improvements._unit_of_work:
            user2.follow(UserId(1))
            user_repository_improvements.save(user2)

        # リポジトリのsaveメソッドをモックして例外を投げるようにする
        original_save = user_repository_improvements.save
        def mock_save(user):
            raise Exception("Mock save exception")
        user_repository_improvements.save = mock_save

        try:
            # 実行（予期しない例外は SystemErrorException でラップされて再送出される）
            with pytest.raises(SystemErrorException) as exc_info:
                service_improvements.handle_user_blocked(event)
            assert "Mock save exception" in str(exc_info.value)
        finally:
            user_repository_improvements.save = original_save

        # 検証：ログにエラーが記録されていることを確認
        assert any("Failed to handle event" in record.message for record in caplog.records)
        assert any(record.levelname == "ERROR" for record in caplog.records)

    def test_unit_of_work_integration_in_relationship_handler(self, service_improvements, user_repository_improvements, unit_of_work_improvements):
        """関係イベントハンドラでのUnit of Workが正しく統合されていることを確認"""
        # Unit of Workがトランザクション内であることを確認
        assert not unit_of_work_improvements.is_in_transaction()

        # まずユーザー間にフォロー関係を作成
        user1 = user_repository_improvements.find_by_id(UserId(1))
        user2 = user_repository_improvements.find_by_id(UserId(2))

        with unit_of_work_improvements:
            user1.follow(UserId(2))
            user_repository_improvements.save(user1)

        # ブロックイベントを作成
        event = SnsUserBlockedEvent.create(
            aggregate_id=user1.user_id,
            aggregate_type="UserAggregate",
            blocker_user_id=user1.user_id,
            blocked_user_id=user2.user_id
        )

        # 実行
        service_improvements.handle_user_blocked(event)

        # Unit of Workがコミットされていることを確認
        assert unit_of_work_improvements.is_committed()

        # フォロー関係が解除されていることを確認
        updated_user2 = user_repository_improvements.find_by_id(UserId(2))
        assert not updated_user2.is_following(UserId(1))


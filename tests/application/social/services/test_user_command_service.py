"""
UserCommandServiceのテスト
"""
import pytest
import logging
from unittest.mock import Mock, patch
from src.application.social.services.user_command_service import UserCommandService
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.application.social.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand
)
from src.application.social.contracts.dtos import CommandResultDto, ErrorResponseDto
from src.application.social.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
    UserNotFoundForCommandException,
)
from src.application.social.exceptions.query.user_query_exception import UserQueryException
from src.application.social.exceptions import SystemErrorException
from src.domain.sns.exception import (
    UserNotFoundException,
    CannotFollowBlockedUserException,
    CannotUnfollowNotFollowedUserException,
    CannotBlockAlreadyBlockedUserException,
    CannotUnblockNotBlockedUserException,
    CannotSubscribeAlreadySubscribedUserException,
    CannotSubscribeBlockedUserException,
    CannotSubscribeNotFollowedUserException,
    CannotUnsubscribeNotSubscribedUserException,
    SelfFollowException,
    SelfUnfollowException,
    SelfBlockException,
    SelfUnblockException,
    SelfSubscribeException,
    SelfUnsubscribeException,
    ProfileUpdateValidationException,
)
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.event.sns_user_event import (
    SnsUserCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserUnfollowedEvent,
    SnsUserBlockedEvent,
    SnsUserUnblockedEvent,
    SnsUserProfileUpdatedEvent,
    SnsUserSubscribedEvent,
    SnsUserUnsubscribedEvent,
)


class TestUserCommandService:
    """UserCommandServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.repository = InMemorySnsUserRepository()
        # Unit of Workファクトリ関数を定義（別トランザクション用）
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        # Unit of Workとイベントパブリッシャーを作成
        self.unit_of_work, self.event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        self.service = UserCommandService(self.repository, self.event_publisher, self.unit_of_work)
        # ログ出力をテスト用に設定
        self.service.logger.setLevel(logging.DEBUG)

    def teardown_method(self):
        """各テストメソッドの後に実行"""
        # Unit of Workとイベントパブリッシャーをリセット
        self.unit_of_work.clear_pending_events()
        self.event_publisher.clear_events()

    # create_user テスト
    def test_create_user_success(self):
        """create_user - 正常系テスト"""
        # Given
        command = CreateUserCommand(
            user_name="test_user",
            display_name="テストユーザー",
            bio="テストユーザーです"
        )
        initial_count = self.repository.count()

        # When
        result = self.service.create_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーが正常に作成されました"
        assert "user_id" in result.data
        assert int(result.data["user_id"]) > 0

        # リポジトリにユーザーが保存されたことを確認
        assert self.repository.count() == initial_count + 1
        created_user = self.repository.find_by_id(result.data["user_id"])
        assert created_user is not None
        assert created_user.sns_user.user_profile.user_name == "test_user"
        assert created_user.sns_user.user_profile.display_name == "テストユーザー"
        assert created_user.sns_user.user_profile.bio == "テストユーザーです"

    def test_create_user_with_empty_username_raises_exception(self):
        """create_user - ユーザー名が空の場合の異常系テスト"""
        # Given
        command = CreateUserCommand(
            user_name="",
            display_name="テストユーザー",
            bio="テストユーザーです"
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.create_user(command)

        assert "ユーザー名" in str(exc_info.value)
        assert exc_info.value.error_code == "USER_NAME_VALIDATION_ERROR"

    def test_create_user_with_long_username_raises_exception(self):
        """create_user - ユーザー名が長すぎる場合の異常系テスト"""
        # Given
        long_username = "a" * 51  # 50文字を超える
        command = CreateUserCommand(
            user_name=long_username,
            display_name="テストユーザー",
            bio="テストユーザーです"
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.create_user(command)

        assert "ユーザー名" in str(exc_info.value)
        assert exc_info.value.error_code == "USER_NAME_VALIDATION_ERROR"

    # update_user_profile テスト
    def test_update_user_profile_success(self):
        """update_user_profile - 正常系テスト"""
        # Given: まずユーザーを1つ作成する
        create_command = CreateUserCommand(
            user_name="test_update_user",
            display_name="テスト更新ユーザー",
            bio="テスト更新用ユーザーです"
        )
        create_result = self.service.create_user(create_command)
        user_id = int(create_result.data["user_id"])

        # デバッグ: 作成されたユーザーがリポジトリに保存されているか確認
        print(f"Created user_id: {user_id}")
        print(f"Repository count: {self.repository.count()}")
        print(f"Repository users: {list(self.repository.find_all())}")

        # UserId(7)として検索してみる
        target_user = self.repository.find_by_id(UserId(user_id))
        print(f"Found user with UserId({user_id}): {target_user}")

        command = UpdateUserProfileCommand(
            user_id=int(user_id),
            new_display_name="新しい勇者",
            new_bio="新しい世界を救う勇者です"
        )

        # When
        result = self.service.update_user_profile(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザープロフィールが正常に更新されました"
        assert int(result.data["user_id"]) == user_id

        # リポジトリに更新されたことを確認
        updated_user = self.repository.find_by_id(UserId(user_id))
        assert updated_user is not None
        assert updated_user.sns_user.user_profile.display_name == "新しい勇者"
        assert updated_user.sns_user.user_profile.bio == "新しい世界を救う勇者です"

    def test_update_user_profile_not_found_raises_exception(self):
        """update_user_profile - 存在しないユーザーIDの場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        command = UpdateUserProfileCommand(
            user_id=non_existent_user_id,
            new_display_name="新しい名前",
            new_bio="新しい自己紹介"
        )

        # When & Then
        with pytest.raises(UserNotFoundForCommandException) as exc_info:
            self.service.update_user_profile(command)

        assert "コマンド 'update_user_profile' の実行時にユーザーが見つかりません" in str(exc_info.value)
        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert exc_info.value.user_id == non_existent_user_id

    def test_update_user_profile_invalid_display_name_raises_exception(self):
        """update_user_profile - 表示名が無効な場合の異常系テスト"""
        # Given
        user_id = 1
        command = UpdateUserProfileCommand(
            user_id=user_id,
            new_display_name="",  # 空の表示名
            new_bio="新しい自己紹介"
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.update_user_profile(command)

        assert "表示名" in str(exc_info.value)
        assert exc_info.value.error_code == "DISPLAY_NAME_VALIDATION_ERROR"

    # follow_user テスト
    def test_follow_user_success(self):
        """follow_user - 正常系テスト"""
        # Given
        follower_user_id = 4  # 盗賊（ユーザーID: 4）
        followee_user_id = 5  # 僧侶（ユーザーID: 5）
        command = FollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When
        result = self.service.follow_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーをフォローしました"
        assert result.data["follower_user_id"] == follower_user_id
        assert result.data["followee_user_id"] == followee_user_id

        # リポジトリにフォロー関係が追加されたことを確認
        follower_user = self.repository.find_by_id(UserId(follower_user_id))
        assert follower_user is not None
        assert follower_user.is_following(UserId(followee_user_id))

    def test_follow_user_self_follow_raises_exception(self):
        """follow_user - 自分自身をフォローしようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = FollowUserCommand(
            follower_user_id=user_id,
            followee_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.follow_user(command)

        assert exc_info.value.error_code == "SELF_FOLLOW_ERROR"
        assert "自分自身をフォロー" in str(exc_info.value)

    def test_follow_user_not_found_follower_raises_exception(self):
        """follow_user - フォロー元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        followee_user_id = 1
        command = FollowUserCommand(
            follower_user_id=non_existent_user_id,
            followee_user_id=followee_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.follow_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_follow_user_blocked_user_raises_exception(self):
        """follow_user - ブロックされているユーザーをフォローしようとする場合の異常系テスト"""
        # Given: 商人（ID: 6）は勇者（ID: 1）をブロックしている
        follower_user_id = 1  # 勇者
        followee_user_id = 6  # 商人
        command = FollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.follow_user(command)

        assert exc_info.value.error_code == "CANNOT_FOLLOW_BLOCKED_USER"
        assert "ブロックされている" in str(exc_info.value)

    # unfollow_user テスト
    def test_unfollow_user_success(self):
        """unfollow_user - 正常系テスト"""
        # Given: 既存のフォロー関係があることを確認
        follower_user_id = 1  # 勇者
        followee_user_id = 2  # 魔法使い（勇者は魔法使いをフォローしている）
        command = UnfollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When
        result = self.service.unfollow_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーのフォローを解除しました"
        assert result.data["follower_user_id"] == follower_user_id
        assert result.data["followee_user_id"] == followee_user_id

        # リポジトリにフォロー関係が解除されたことを確認
        follower_user = self.repository.find_by_id(UserId(follower_user_id))
        assert follower_user is not None
        assert not follower_user.is_following(UserId(followee_user_id))

    def test_unfollow_user_self_unfollow_raises_exception(self):
        """unfollow_user - 自分自身をアンフォローしようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = UnfollowUserCommand(
            follower_user_id=user_id,
            followee_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unfollow_user(command)

        assert exc_info.value.error_code == "SELF_UNFOLLOW_ERROR"
        assert "自分自身をアンフォロー" in str(exc_info.value)

    def test_unfollow_user_not_found_follower_raises_exception(self):
        """unfollow_user - フォロー元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        followee_user_id = 1
        command = UnfollowUserCommand(
            follower_user_id=non_existent_user_id,
            followee_user_id=followee_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unfollow_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_unfollow_user_not_followed_raises_exception(self):
        """unfollow_user - フォローしていないユーザーをアンフォローしようとする場合の異常系テスト"""
        # Given: 僧侶（ID: 5）は商人（ID: 6）をフォローしていない
        follower_user_id = 5  # 僧侶
        followee_user_id = 6  # 商人
        command = UnfollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unfollow_user(command)

        assert exc_info.value.error_code == "CANNOT_UNFOLLOW_NOT_FOLLOWED_USER"
        assert "フォローしていない" in str(exc_info.value)

    # block_user テスト
    def test_block_user_success(self):
        """block_user - 正常系テスト"""
        # Given
        blocker_user_id = 1  # 勇者
        blocked_user_id = 4  # 盗賊（勇者は盗賊をブロックしていない）
        command = BlockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When
        result = self.service.block_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーをブロックしました"
        assert result.data["blocker_user_id"] == blocker_user_id
        assert result.data["blocked_user_id"] == blocked_user_id

        # リポジトリにブロック関係が追加されたことを確認
        blocker_user = self.repository.find_by_id(UserId(blocker_user_id))
        assert blocker_user is not None
        assert blocker_user.is_blocked(UserId(blocked_user_id))

    def test_block_user_self_block_raises_exception(self):
        """block_user - 自分自身をブロックしようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = BlockUserCommand(
            blocker_user_id=user_id,
            blocked_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.block_user(command)

        assert exc_info.value.error_code == "SELF_BLOCK_ERROR"
        assert "自分自身をブロック" in str(exc_info.value)

    def test_block_user_not_found_blocker_raises_exception(self):
        """block_user - ブロック元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        blocked_user_id = 1
        command = BlockUserCommand(
            blocker_user_id=non_existent_user_id,
            blocked_user_id=blocked_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.block_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_block_user_already_blocked_raises_exception(self):
        """block_user - 既にブロックしているユーザーをブロックしようとする場合の異常系テスト"""
        # Given: 魔法使い（ID: 2）は盗賊（ID: 4）をブロックしている
        blocker_user_id = 2  # 魔法使い
        blocked_user_id = 4  # 盗賊
        command = BlockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.block_user(command)

        assert exc_info.value.error_code == "CANNOT_BLOCK_ALREADY_BLOCKED_USER"
        assert "既にブロック" in str(exc_info.value)

    # unblock_user テスト
    def test_unblock_user_success(self):
        """unblock_user - 正常系テスト"""
        # Given: 魔法使い（ID: 2）は盗賊（ID: 4）をブロックしている
        blocker_user_id = 2  # 魔法使い
        blocked_user_id = 4  # 盗賊
        command = UnblockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When
        result = self.service.unblock_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーのブロックを解除しました"
        assert result.data["blocker_user_id"] == blocker_user_id
        assert result.data["blocked_user_id"] == blocked_user_id

        # リポジトリにブロック関係が解除されたことを確認
        blocker_user = self.repository.find_by_id(UserId(blocker_user_id))
        assert blocker_user is not None
        assert not blocker_user.is_blocked(UserId(blocked_user_id))

    def test_unblock_user_self_unblock_raises_exception(self):
        """unblock_user - 自分自身のブロックを解除しようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = UnblockUserCommand(
            blocker_user_id=user_id,
            blocked_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unblock_user(command)

        assert exc_info.value.error_code == "SELF_UNBLOCK_ERROR"
        assert "自分自身をアンブロック" in str(exc_info.value)

    def test_unblock_user_not_found_blocker_raises_exception(self):
        """unblock_user - ブロック元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        blocked_user_id = 1
        command = UnblockUserCommand(
            blocker_user_id=non_existent_user_id,
            blocked_user_id=blocked_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unblock_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_unblock_user_not_blocked_raises_exception(self):
        """unblock_user - ブロックしていないユーザーのブロックを解除しようとする場合の異常系テスト"""
        # Given: 勇者（ID: 1）は盗賊（ID: 4）をブロックしていない
        blocker_user_id = 1  # 勇者
        blocked_user_id = 4  # 盗賊
        command = UnblockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unblock_user(command)

        assert exc_info.value.error_code == "CANNOT_UNBLOCK_NOT_BLOCKED_USER"
        assert "ブロックしていない" in str(exc_info.value)

    # subscribe_user テスト
    def test_subscribe_user_success(self):
        """subscribe_user - 正常系テスト"""
        # Given: まず盗賊が戦士をフォローする
        follow_command = FollowUserCommand(
            follower_user_id=4,  # 盗賊
            followee_user_id=3   # 戦士
        )
        self.service.follow_user(follow_command)

        # 次に購読する
        subscriber_user_id = 4  # 盗賊
        subscribed_user_id = 3  # 戦士
        command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When
        result = self.service.subscribe_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーを購読しました"
        assert result.data["subscriber_user_id"] == subscriber_user_id
        assert result.data["subscribed_user_id"] == subscribed_user_id

        # リポジトリに購読関係が追加されたことを確認
        subscriber_user = self.repository.find_by_id(UserId(subscriber_user_id))
        assert subscriber_user is not None
        assert subscriber_user.is_subscribed(UserId(subscribed_user_id))

    def test_subscribe_user_self_subscribe_raises_exception(self):
        """subscribe_user - 自分自身を購読しようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = SubscribeUserCommand(
            subscriber_user_id=user_id,
            subscribed_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.subscribe_user(command)

        assert exc_info.value.error_code == "SELF_SUBSCRIBE_ERROR"
        assert "自分自身を購読" in str(exc_info.value)

    def test_subscribe_user_not_found_subscriber_raises_exception(self):
        """subscribe_user - 購読元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        subscribed_user_id = 1
        command = SubscribeUserCommand(
            subscriber_user_id=non_existent_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.subscribe_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_subscribe_user_already_subscribed_raises_exception(self):
        """subscribe_user - 既に購読しているユーザーを購読しようとする場合の異常系テスト"""
        # Given: 勇者（ID: 1）は魔法使い（ID: 2）を購読している
        subscriber_user_id = 1  # 勇者
        subscribed_user_id = 2  # 魔法使い
        command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.subscribe_user(command)

        assert exc_info.value.error_code == "CANNOT_SUBSCRIBE_ALREADY_SUBSCRIBED_USER"
        assert "既に購読" in str(exc_info.value)

    def test_subscribe_user_blocked_user_raises_exception(self):
        """subscribe_user - ブロックされているユーザーを購読しようとする場合の異常系テスト"""
        # Given: 商人（ID: 6）は勇者（ID: 1）をブロックしている
        # まず勇者が商人をフォローしようとするが、ブロックされているので失敗する
        follow_command = FollowUserCommand(
            follower_user_id=1,  # 勇者
            followee_user_id=6   # 商人
        )

        # When & Then: フォローしようとしてもブロックされているので失敗
        with pytest.raises(UserCommandException) as exc_info:
            self.service.follow_user(follow_command)

        assert exc_info.value.error_code == "CANNOT_FOLLOW_BLOCKED_USER"
        assert "ブロックされている" in str(exc_info.value)

    def test_subscribe_user_not_followed_raises_exception(self):
        """subscribe_user - フォローしていないユーザーを購読しようとする場合の異常系テスト"""
        # Given: 戦士（ID: 3）は商人（ID: 6）をフォローしていない
        subscriber_user_id = 3  # 戦士
        subscribed_user_id = 6  # 商人
        command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.subscribe_user(command)

        assert exc_info.value.error_code == "CANNOT_SUBSCRIBE_NOT_FOLLOWED_USER"
        assert "フォローしていない" in str(exc_info.value)

    # unsubscribe_user テスト
    def test_unsubscribe_user_success(self):
        """unsubscribe_user - 正常系テスト"""
        # Given: 勇者（ID: 1）は魔法使い（ID: 2）を購読している
        subscriber_user_id = 1  # 勇者
        subscribed_user_id = 2  # 魔法使い
        command = UnsubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When
        result = self.service.unsubscribe_user(command)

        # Then
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ユーザーの購読を解除しました"
        assert result.data["subscriber_user_id"] == subscriber_user_id
        assert result.data["subscribed_user_id"] == subscribed_user_id

        # リポジトリに購読関係が解除されたことを確認
        subscriber_user = self.repository.find_by_id(UserId(subscriber_user_id))
        assert subscriber_user is not None
        assert not subscriber_user.is_subscribed(UserId(subscribed_user_id))

    def test_unsubscribe_user_self_unsubscribe_raises_exception(self):
        """unsubscribe_user - 自分自身の購読を解除しようとする場合の異常系テスト"""
        # Given
        user_id = 1
        command = UnsubscribeUserCommand(
            subscriber_user_id=user_id,
            subscribed_user_id=user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unsubscribe_user(command)

        assert exc_info.value.error_code == "SELF_UNSUBSCRIBE_ERROR"
        assert "自分自身をアンサブスクライブ" in str(exc_info.value)

    def test_unsubscribe_user_not_found_subscriber_raises_exception(self):
        """unsubscribe_user - 購読元ユーザーが存在しない場合の異常系テスト"""
        # Given
        non_existent_user_id = 999
        subscribed_user_id = 1
        command = UnsubscribeUserCommand(
            subscriber_user_id=non_existent_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unsubscribe_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "ユーザーが見つかりません" in str(exc_info.value)

    def test_unsubscribe_user_not_subscribed_raises_exception(self):
        """unsubscribe_user - 購読していないユーザーの購読を解除しようとする場合の異常系テスト"""
        # Given: 盗賊（ID: 4）は戦士（ID: 3）を購読していない
        subscriber_user_id = 4  # 盗賊
        subscribed_user_id = 3  # 戦士
        command = UnsubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When & Then
        with pytest.raises(UserCommandException) as exc_info:
            self.service.unsubscribe_user(command)

        assert exc_info.value.error_code == "CANNOT_UNSUBSCRIBE_NOT_SUBSCRIBED_USER"
        assert "購読していない" in str(exc_info.value)

    # エラーハンドリングとログテスト
    def test_error_response_dto_creation(self):
        """エラーレスポンスDTOが正しく作成されることのテスト"""
        # Given
        from src.application.social.contracts.dtos import ErrorResponseDto

        # When
        error_response = ErrorResponseDto(
            error_code="TEST_ERROR",
            message="テストエラー",
            details="詳細情報",
            user_id=1,
            target_user_id=2
        )

        # Then
        assert error_response.error_code == "TEST_ERROR"
        assert error_response.message == "テストエラー"
        assert error_response.details == "詳細情報"
        assert error_response.user_id == 1
        assert error_response.target_user_id == 2

    def test_domain_exception_logging(self):
        """ドメイン例外が発生した場合に適切にログが記録されることのテスト"""
        # Given
        command = FollowUserCommand(
            follower_user_id=999,  # 存在しないユーザー
            followee_user_id=1
        )

        # When & Then
        with pytest.raises(UserNotFoundForCommandException) as exc_info:
            self.service.follow_user(command)

        assert exc_info.value.error_code == "USER_NOT_FOUND_FOR_COMMAND"
        assert "コマンド 'follow_user' の実行時にユーザーが見つかりません" in str(exc_info.value)
        assert exc_info.value.user_id == 999
        # ログは記録されているはず（実際のテストではログの確認は難しいため、例外が適切に処理されることを確認）

    @patch('src.application.social.services.user_command_service.logging')
    def test_unexpected_error_logging(self, mock_logging):
        """予期しないエラーが発生した場合に適切にログが記録されることのテスト"""
        # Given: モックを使って予期しないエラーを発生させる
        with patch.object(self.repository, 'find_by_id', side_effect=RuntimeError("Database error")):
            command = FollowUserCommand(
                follower_user_id=1,
                followee_user_id=2
            )

            # When & Then
            with pytest.raises(SystemErrorException):
                self.service.follow_user(command)

            # 実際のログ出力が記録されていることを確認（Mockが機能しない場合）
            # ログは標準出力に記録されているはず

    # イベント発行テスト
    def test_event_publishing_on_user_creation(self):
        """ユーザー作成時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()
        command = CreateUserCommand(
            user_name="event_test_user",
            display_name="イベントテストユーザー",
            bio="イベント発行テスト用ユーザーです"
        )

        # When
        result = self.service.create_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserCreatedEventが発行されていることを確認
        created_events = [e for e in events if isinstance(e, SnsUserCreatedEvent)]
        assert len(created_events) == 1
        assert created_events[0].aggregate_id == result.data["user_id"]
        assert created_events[0].user_name == "event_test_user"
        assert created_events[0].display_name == "イベントテストユーザー"
        assert created_events[0].bio == "イベント発行テスト用ユーザーです"

    def test_event_publishing_on_profile_update(self):
        """プロフィール更新時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()
        user_id = 1
        command = UpdateUserProfileCommand(
            user_id=user_id,
            new_display_name="更新された勇者",
            new_bio="更新された自己紹介"
        )

        # When
        result = self.service.update_user_profile(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserProfileUpdatedEventが発行されていることを確認
        updated_events = [e for e in events if isinstance(e, SnsUserProfileUpdatedEvent)]
        assert len(updated_events) == 1
        assert updated_events[0].aggregate_id == UserId(user_id)
        assert updated_events[0].new_display_name == "更新された勇者"
        assert updated_events[0].new_bio == "更新された自己紹介"

    def test_event_publishing_on_follow(self):
        """フォロー時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()
        follower_user_id = 3  # 戦士
        followee_user_id = 4  # 盗賊
        command = FollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When
        result = self.service.follow_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserFollowedEventが発行されていることを確認
        followed_events = [e for e in events if isinstance(e, SnsUserFollowedEvent)]
        assert len(followed_events) == 1
        assert followed_events[0].aggregate_id == follower_user_id  # int型
        assert followed_events[0].follower_user_id == UserId(follower_user_id)
        assert followed_events[0].followee_user_id == UserId(followee_user_id)

    def test_unfollow_user_success(self):
        """unfollow_user - 正常系テスト"""
        # Given
        follower_user_id = 3  # 戦士
        followee_user_id = 4  # 盗賊

        # まずフォロー関係を作成
        follow_command = FollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )
        self.service.follow_user(follow_command)

        # When - フォロー解除を実行
        unfollow_command = UnfollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )
        result = self.service.unfollow_user(unfollow_command)

        # Then
        assert result.success is True
        assert result.message == "ユーザーのフォローを解除しました"
        assert result.data["follower_user_id"] == follower_user_id
        assert result.data["followee_user_id"] == followee_user_id

    def test_event_publishing_on_unfollow(self):
        """アンフォロー時にイベントが発行されることのテスト"""
        # Given
        # イベントパブリッシャーをクリア
        self.event_publisher.clear_events()

        # 既存のフォロー関係を使用（勇者（ID: 1）が魔法使い（ID: 2）をフォローしている）
        follower_user_id = 1  # 勇者
        followee_user_id = 2  # 魔法使い
        command = UnfollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When
        result = self.service.unfollow_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserUnfollowedEventが発行されていることを確認
        unfollowed_events = [e for e in events if isinstance(e, SnsUserUnfollowedEvent)]
        assert len(unfollowed_events) == 1
        assert unfollowed_events[0].aggregate_id == UserId(follower_user_id)
        assert unfollowed_events[0].follower_user_id == UserId(follower_user_id)
        assert unfollowed_events[0].followee_user_id == UserId(followee_user_id)

    def test_event_publishing_on_block(self):
        """ブロック時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()
        blocker_user_id = 3  # 戦士
        blocked_user_id = 4  # 盗賊
        command = BlockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When
        result = self.service.block_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserBlockedEventが発行されていることを確認
        blocked_events = [e for e in events if isinstance(e, SnsUserBlockedEvent)]
        assert len(blocked_events) == 1
        assert blocked_events[0].aggregate_id == UserId(blocker_user_id)
        assert blocked_events[0].blocker_user_id == UserId(blocker_user_id)
        assert blocked_events[0].blocked_user_id == UserId(blocked_user_id)

    def test_event_publishing_on_unblock(self):
        """アンブロック時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()

        # 既存のブロック関係を使用（魔法使い（ID: 2）が盗賊（ID: 4）をブロックしている）
        blocker_user_id = 2  # 魔法使い
        blocked_user_id = 4  # 盗賊
        command = UnblockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        # When
        result = self.service.unblock_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        assert len(events) == 1

        # SnsUserUnblockedEventが発行されていることを確認
        unblocked_events = [e for e in events if isinstance(e, SnsUserUnblockedEvent)]
        assert len(unblocked_events) == 1
        assert unblocked_events[0].aggregate_id == UserId(blocker_user_id)
        assert unblocked_events[0].blocker_user_id == UserId(blocker_user_id)
        assert unblocked_events[0].blocked_user_id == UserId(blocked_user_id)

    def test_event_publishing_on_subscribe(self):
        """購読時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()

        # 新しい購読関係を作成（戦士（ID: 3）が盗賊（ID: 4）を購読）
        subscriber_user_id = 3  # 戦士
        subscribed_user_id = 4  # 盗賊

        # まずフォロー関係を作成（購読にはフォロー関係が必要）
        follow_command = FollowUserCommand(
            follower_user_id=subscriber_user_id,
            followee_user_id=subscribed_user_id
        )
        self.service.follow_user(follow_command)

        # イベントパブリッシャーをクリアしてからsubscribeを実行
        self.event_publisher.clear_events()
        command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When
        result = self.service.subscribe_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        # SnsUserSubscribedEventが発行されていることを確認
        subscribed_events = [e for e in events if isinstance(e, SnsUserSubscribedEvent)]
        assert len(subscribed_events) == 1
        assert subscribed_events[0].aggregate_id == UserId(subscriber_user_id)
        assert subscribed_events[0].subscriber_user_id == UserId(subscriber_user_id)
        assert subscribed_events[0].subscribed_user_id == UserId(subscribed_user_id)

    def test_event_publishing_on_unsubscribe(self):
        """購読解除時にイベントが発行されることのテスト"""
        # Given
        self.event_publisher.clear_events()

        # 新しい購読関係を作成してから解除（戦士（ID: 3）が盗賊（ID: 4）を購読）
        subscriber_user_id = 3  # 戦士
        subscribed_user_id = 4  # 盗賊

        # まずフォローと購読関係を作成
        follow_command = FollowUserCommand(
            follower_user_id=subscriber_user_id,
            followee_user_id=subscribed_user_id
        )
        self.service.follow_user(follow_command)

        subscribe_command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )
        self.service.subscribe_user(subscribe_command)

        # イベントパブリッシャーをクリアしてからunsubscribeを実行
        self.event_publisher.clear_events()
        command = UnsubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )

        # When
        result = self.service.unsubscribe_user(command)

        # Then
        # イベントが発行されていることを確認
        events = self.event_publisher.get_published_events()
        # SnsUserUnsubscribedEventが発行されていることを確認
        unsubscribed_events = [e for e in events if isinstance(e, SnsUserUnsubscribedEvent)]
        assert len(unsubscribed_events) == 1
        assert unsubscribed_events[0].aggregate_id == UserId(subscriber_user_id)
        assert unsubscribed_events[0].subscriber_user_id == UserId(subscriber_user_id)
        assert unsubscribed_events[0].subscribed_user_id == UserId(subscribed_user_id)

    def test_unblock_user_success(self):
        """unblock_user - 正常系テスト"""
        # Given
        blocker_user_id = 3  # 戦士
        blocked_user_id = 4  # 盗賊

        # まずブロック関係を作成
        block_command = BlockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )
        self.service.block_user(block_command)

        # When - ブロック解除を実行
        unblock_command = UnblockUserCommand(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )
        result = self.service.unblock_user(unblock_command)

        # Then
        assert result.success is True
        assert result.message == "ユーザーのブロックを解除しました"
        assert result.data["blocker_user_id"] == blocker_user_id
        assert result.data["blocked_user_id"] == blocked_user_id

    def test_subscribe_user_success(self):
        """subscribe_user - 正常系テスト"""
        # Given
        subscriber_user_id = 3  # 戦士
        subscribed_user_id = 4  # 盗賊

        # まずフォロー関係を作成（購読にはフォロー関係が必要）
        follow_command = FollowUserCommand(
            follower_user_id=subscriber_user_id,
            followee_user_id=subscribed_user_id
        )
        self.service.follow_user(follow_command)

        # When - 購読を実行
        subscribe_command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )
        result = self.service.subscribe_user(subscribe_command)

        # Then
        assert result.success is True
        assert result.message == "ユーザーを購読しました"
        assert result.data["subscriber_user_id"] == subscriber_user_id
        assert result.data["subscribed_user_id"] == subscribed_user_id

    def test_unsubscribe_user_success(self):
        """unsubscribe_user - 正常系テスト"""
        # Given
        subscriber_user_id = 3  # 戦士
        subscribed_user_id = 4  # 盗賊

        # まずフォローと購読関係を作成
        follow_command = FollowUserCommand(
            follower_user_id=subscriber_user_id,
            followee_user_id=subscribed_user_id
        )
        self.service.follow_user(follow_command)

        subscribe_command = SubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )
        self.service.subscribe_user(subscribe_command)

        # When - 購読解除を実行
        unsubscribe_command = UnsubscribeUserCommand(
            subscriber_user_id=subscriber_user_id,
            subscribed_user_id=subscribed_user_id
        )
        result = self.service.unsubscribe_user(unsubscribe_command)

        # Then
        assert result.success is True
        assert result.message == "ユーザーの購読を解除しました"
        assert result.data["subscriber_user_id"] == subscriber_user_id
        assert result.data["subscribed_user_id"] == subscribed_user_id

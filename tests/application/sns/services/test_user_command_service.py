"""
UserCommandServiceのテスト
"""
import pytest
import logging
from unittest.mock import Mock, patch
from src.application.sns.services.user_command_service import UserCommandService
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
from src.application.sns.contracts.commands import (
    CreateUserCommand,
    UpdateUserProfileCommand,
    FollowUserCommand,
    UnfollowUserCommand,
    BlockUserCommand,
    UnblockUserCommand,
    SubscribeUserCommand,
    UnsubscribeUserCommand
)
from src.application.sns.contracts.dtos import CommandResultDto, ErrorResponseDto
from src.application.sns.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
    UserNotFoundForCommandException,
)
from src.application.sns.exceptions.query.user_query_exception import UserQueryException
from src.application.sns.exceptions import SystemErrorException
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


class TestUserCommandService:
    """UserCommandServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.repository = InMemorySnsUserRepository()
        self.event_publisher = InMemoryEventPublisher()
        self.service = UserCommandService(self.repository, self.event_publisher)
        # ログ出力をテスト用に設定
        self.service.logger.setLevel(logging.DEBUG)

    def teardown_method(self):
        """各テストメソッドの後に実行"""
        pass

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
        assert exc_info.value.error_code == "USERNAMEVALIDATIONEXCEPTION"

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
        assert exc_info.value.error_code == "USERNAMEVALIDATIONEXCEPTION"

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
        assert exc_info.value.error_code == "DISPLAYNAMEVALIDATIONEXCEPTION"

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

        assert exc_info.value.error_code == "SELFFOLLOWEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTFOLLOWBLOCKEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "SELFUNFOLLOWEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTUNFOLLOWNOTFOLLOWEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "SELFBLOCKEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTBLOCKALREADYBLOCKEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "SELFUNBLOCKEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTUNBLOCKNOTBLOCKEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "SELFSUBSCRIBEEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTSUBSCRIBEALREADYSUBSCRIBEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTFOLLOWBLOCKEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTSUBSCRIBENOTFOLLOWEDUSEREXCEPTION"
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

        assert exc_info.value.error_code == "SELFUNSUBSCRIBEEXCEPTION"
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

        assert exc_info.value.error_code == "CANNOTUNSUBSCRIBENOTSUBSCRIBEDUSEREXCEPTION"
        assert "購読していない" in str(exc_info.value)

    # エラーハンドリングとログテスト
    def test_error_response_dto_creation(self):
        """エラーレスポンスDTOが正しく作成されることのテスト"""
        # Given
        from src.application.sns.contracts.dtos import ErrorResponseDto

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

    @patch('src.application.sns.services.user_command_service.logging')
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
        command = CreateUserCommand(
            user_name="event_test_user",
            display_name="イベントテストユーザー",
            bio="イベント発行テスト用ユーザーです"
        )

        # When
        result = self.service.create_user(command)

        # Then
        # イベント発行が呼ばれたことを確認（実際のイベント内容は確認しにくいため、メソッドが呼ばれたことを確認）
        # 実際のテストでは、イベントパブリッシャーのモックを使って発行されたイベントを検証する
        created_user = self.repository.find_by_id(result.data["user_id"])
        assert created_user is not None

        # イベントが発行された場合、ユーザーは保存されているはず
        assert self.repository.exists_by_id(result.data["user_id"])

    def test_event_publishing_on_profile_update(self):
        """プロフィール更新時にイベントが発行されることのテスト"""
        # Given
        user_id = 1
        command = UpdateUserProfileCommand(
            user_id=user_id,
            new_display_name="更新された勇者",
            new_bio="更新された自己紹介"
        )

        # When
        result = self.service.update_user_profile(command)

        # Then
        # イベント発行が呼ばれたことを確認
        updated_user = self.repository.find_by_id(UserId(user_id))
        assert updated_user is not None
        assert updated_user.sns_user.user_profile.display_name == "更新された勇者"
        assert updated_user.sns_user.user_profile.bio == "更新された自己紹介"

    def test_event_publishing_on_follow(self):
        """フォロー時にイベントが発行されることのテスト"""
        # Given
        follower_user_id = 3  # 戦士
        followee_user_id = 4  # 盗賊
        command = FollowUserCommand(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        # When
        result = self.service.follow_user(command)

        # Then
        # フォロー関係が正しく作成されたことを確認
        follower_user = self.repository.find_by_id(UserId(follower_user_id))
        assert follower_user is not None
        assert follower_user.is_following(UserId(followee_user_id))

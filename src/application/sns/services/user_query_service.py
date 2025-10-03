from typing import List, Optional, Tuple, Callable, Any, TYPE_CHECKING
import logging
from functools import wraps

if TYPE_CHECKING:
    from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.enum import UserRelationshipType
from src.domain.sns.repository import UserRepository
from src.domain.sns.value_object import UserId
from src.domain.sns.exception import (
    SnsDomainException,
    UserNotFoundException,
)
from src.application.sns.contracts.commands import GetUserProfilesCommand
from src.application.sns.exceptions import ApplicationException
from src.application.sns.contracts.dtos import UserProfileDto, ErrorResponseDto
from src.application.sns.exceptions import (
    UserQueryException,
    SystemErrorException,
    ApplicationExceptionFactory,
)


class UserQueryService:
    """ユーザー検索サービス"""

    def __init__(self, user_repository: UserRepository):
        self._user_repository = user_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except ApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except SnsDomainException as e:
            raise ApplicationExceptionFactory.create_from_domain_exception(
                e,
                user_id=context.get('user_id'),
                target_user_id=context.get('target_user_id')
            )
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)


    
    def show_my_profile(self, viewer_user_id: int) -> UserProfileDto:
        """自分のプロフィールを表示"""
        return self._execute_with_error_handling(
            operation=lambda: self._show_my_profile_impl(viewer_user_id),
            context={
                "action": "show_my_profile",
                "user_id": viewer_user_id
            }
        )

    def _show_my_profile_impl(self, viewer_user_id: int) -> UserProfileDto:
        """自分のプロフィールを表示の実装"""
        user_aggregate = self._user_repository.find_by_id(UserId(viewer_user_id))
        if user_aggregate is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")
        followee_count = self._user_repository.count_followees(UserId(viewer_user_id))
        follower_count = self._user_repository.count_followers(UserId(viewer_user_id))
        user_profile_info = user_aggregate.get_user_profile_info()
        return UserProfileDto(
            user_id=user_profile_info["user_id"],
            user_name=user_profile_info["user_name"],
            display_name=user_profile_info["display_name"],
            bio=user_profile_info["bio"],
            is_following=None,
            is_followed_by=None,
            is_blocked=None,
            is_blocked_by=None,
            is_subscribed=None,
            is_subscribed_by=None,
            followee_count=followee_count,
            follower_count=follower_count,
        )

    def show_other_user_profile(self, other_user_id: int, viewer_user_id: int) -> UserProfileDto:
        """他のユーザーのプロフィールを表示"""
        return self._execute_with_error_handling(
            operation=lambda: self._show_other_user_profile_impl(other_user_id, viewer_user_id),
            context={
                "action": "show_other_user_profile",
                "user_id": viewer_user_id,
                "target_user_id": other_user_id
            }
        )

    def _show_other_user_profile_impl(self, other_user_id: int, viewer_user_id: int) -> UserProfileDto:
        """他のユーザーのプロフィールを表示の実装"""
        other_user_aggregate = self._user_repository.find_by_id(UserId(other_user_id))
        if other_user_aggregate is None:
            raise UserNotFoundException(other_user_id, f"ユーザーが見つかりません: {other_user_id}")
        other_user_followee_count = self._user_repository.count_followees(UserId(other_user_id))
        other_user_follower_count = self._user_repository.count_followers(UserId(other_user_id))
        my_user_aggregate = self._user_repository.find_by_id(UserId(viewer_user_id))
        if my_user_aggregate is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")

        other_user_profile_info = other_user_aggregate.get_user_profile_info()
        relationship_status_from_me = my_user_aggregate.relationship_between(UserId(other_user_id))
        relationship_status_to_me = other_user_aggregate.relationship_between(UserId(viewer_user_id))

        return UserProfileDto(
            user_id=other_user_profile_info["user_id"],
            user_name=other_user_profile_info["user_name"],
            display_name=other_user_profile_info["display_name"],
            bio=other_user_profile_info["bio"],
            is_following=relationship_status_from_me["is_following"],
            is_followed_by=relationship_status_to_me["is_following"],
            is_blocked=relationship_status_from_me["is_blocked"],
            is_blocked_by=relationship_status_to_me["is_blocked"],
            is_subscribed=relationship_status_from_me["is_subscribed"],
            is_subscribed_by=relationship_status_to_me["is_subscribed"],
            followee_count=other_user_followee_count,
            follower_count=other_user_follower_count,
        )

    def _get_users_profile_info(self, other_user_ids: List[UserId], viewer_user_id: int) -> List[UserProfileDto]:
        """複数のユーザーのプロフィール情報を取得（汎用）"""
        other_user_aggregates = self._user_repository.find_by_ids(other_user_ids)
        viewer_user_aggregate = self._user_repository.find_by_id(UserId(viewer_user_id))
        if viewer_user_aggregate is None:
            raise UserNotFoundException(viewer_user_id, f"ユーザーが見つかりません: {viewer_user_id}")
        user_profile_infos = [other_user_aggregate.get_user_profile_info() for other_user_aggregate in other_user_aggregates]
        relationship_status_from_me = [viewer_user_aggregate.relationship_between(other_user_id) for other_user_id in other_user_ids]
        relationship_status_to_me = [other_user_aggregate.relationship_between(UserId(viewer_user_id)) for other_user_aggregate in other_user_aggregates]
        followee_counts = [self._user_repository.count_followees(other_user_id) for other_user_id in other_user_ids]
        follower_counts = [self._user_repository.count_followers(other_user_id) for other_user_id in other_user_ids]

        return [UserProfileDto(
            user_id=user_profile_info["user_id"],
            user_name=user_profile_info["user_name"],
            display_name=user_profile_info["display_name"],
            bio=user_profile_info["bio"],
            is_following=rs_from_me["is_following"],
            is_followed_by=rs_to_me["is_following"],
            is_blocked=rs_from_me["is_blocked"],
            is_blocked_by=rs_to_me["is_blocked"],
            is_subscribed=rs_from_me["is_subscribed"],
            is_subscribed_by=rs_to_me["is_subscribed"],
            followee_count=followee_count,
            follower_count=follower_count,
        ) for user_profile_info, rs_from_me, rs_to_me, followee_count, follower_count in zip(user_profile_infos, relationship_status_from_me, relationship_status_to_me, followee_counts, follower_counts)]

    def get_user_profiles(self, command: GetUserProfilesCommand) -> List[UserProfileDto]:
        """ユーザー関係性のプロフィール情報を取得（汎用）

        Args:
            command: プロフィール取得コマンド

        Returns:
            関係性を持つユーザーのプロフィール情報リスト
        """
        return self._execute_with_error_handling(
            operation=lambda: self._get_user_profiles_impl(command),
            context={
                "action": "get_user_profiles",
                "user_id": command.viewer_user_id
            }
        )

    def _get_user_profiles_impl(self, command: GetUserProfilesCommand) -> List[UserProfileDto]:
        """ユーザー関係性のプロフィール情報を取得の実装"""
        # リレーション取得関数を関係性タイプに基づいて選択
        relationship_getter = self._get_relationship_getter(command.relationship_type)
        viewer_user_id = command.viewer_user_id
        related_user_ids = relationship_getter(UserId(viewer_user_id))
        related_user_profile_infos = self._get_users_profile_info(related_user_ids, viewer_user_id)
        return related_user_profile_infos

    def _get_relationship_getter(self, relationship_type: UserRelationshipType):
        """関係性タイプに応じた取得関数を取得"""
        relationship_getter_map = {
            UserRelationshipType.FOLLOWEES: self._user_repository.find_followees,
            UserRelationshipType.FOLLOWERS: self._user_repository.find_followers,
            UserRelationshipType.BLOCKED_USERS: self._user_repository.find_blocked_users,
            UserRelationshipType.BLOCKERS: self._user_repository.find_blockers,
            UserRelationshipType.SUBSCRIPTIONS: self._user_repository.find_subscriptions,
            UserRelationshipType.SUBSCRIBERS: self._user_repository.find_subscribers,
        }
        return relationship_getter_map[relationship_type]
        
    def show_followees_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーのフォローしているユーザーのプロフィールを表示"""
        # TODO: レポジトリにN+1回のクエリが発行される可能性あり
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.FOLLOWEES
        )
        return self.get_user_profiles(command)

    def show_followers_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーのフォロワーのプロフィールを表示"""
        # TODO: レポジトリにN+1回のクエリが発行される可能性あり
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.FOLLOWERS
        )
        return self.get_user_profiles(command)

    def show_blocked_users_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーのブロックしているユーザーのプロフィールを表示"""
        # TODO: レポジトリにN+1回のクエリが発行される可能性あり
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.BLOCKED_USERS
        )
        return self.get_user_profiles(command)

    def show_blockers_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーをブロックしているユーザーのプロフィールを表示"""
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.BLOCKERS
        )
        return self.get_user_profiles(command)

    def show_subscriptions_users_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーの購読しているユーザーのプロフィールを表示"""
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.SUBSCRIPTIONS
        )
        return self.get_user_profiles(command)

    def show_subscribers_users_profile(self, viewer_user_id: int) -> List[UserProfileDto]:
        """ユーザーを購読しているユーザーのプロフィールを表示"""
        command = GetUserProfilesCommand(
            viewer_user_id=viewer_user_id,
            relationship_type=UserRelationshipType.SUBSCRIBERS
        )
        return self.get_user_profiles(command)
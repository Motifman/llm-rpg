from abc import abstractmethod
from typing import List, Optional, Dict
from src.domain.common.repository import Repository
from src.domain.sns.aggregate import ReplyAggregate
from src.domain.sns.value_object import Mention, PostId, ReplyId, UserId


class ReplyRepository(Repository[ReplyAggregate]):
    """ReplyAggregateのリポジトリインターフェース"""

    @abstractmethod
    def find_by_post_id(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得"""
        pass

    @abstractmethod
    def find_by_post_id_include_deleted(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得（削除済みを含む）"""
        pass

    @abstractmethod
    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のユーザーのリプライ一覧を取得"""
        pass

    @abstractmethod
    def find_by_parent_reply_id(self, parent_reply_id: ReplyId, limit: int = 20) -> List[ReplyAggregate]:
        """特定の親リプライへのリプライ一覧を取得（スレッド表示用）"""
        pass

    @abstractmethod
    def find_replies_mentioning_user(self, user_name: str, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーをメンションしたリプライを取得"""
        pass

    @abstractmethod
    def find_replies_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーがいいねしたリプライ一覧を取得"""
        pass

    @abstractmethod
    def find_replies_with_parent_posts(self, limit: int = 20) -> List[tuple]:
        """リプライとその親ポストの情報をまとめて取得"""
        pass

    @abstractmethod
    def search_replies_by_content(self, query: str, limit: int = 20) -> List[ReplyAggregate]:
        """コンテンツでリプライを検索"""
        pass

    @abstractmethod
    def get_reply_count(self, post_id: PostId) -> int:
        """特定のポストへのリプライ数を取得"""
        pass

    @abstractmethod
    def find_thread_replies(self, root_post_id: PostId, max_depth: int = 3) -> Dict[PostId, List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用）"""
        pass

    @abstractmethod
    def find_thread_replies_include_deleted(self, root_post_id: PostId, max_depth: int = 3) -> Dict[PostId, List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用、削除済みを含む）"""
        pass

    @abstractmethod
    def find_replies_by_post_ids(self, post_ids: List[PostId]) -> Dict[PostId, List[ReplyAggregate]]:
        """複数のポストへのリプライを取得"""
        pass

    @abstractmethod
    def get_user_reply_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーのリプライ統計を取得"""
        pass

    @abstractmethod
    def find_recent_replies(self, limit: int = 20) -> List[ReplyAggregate]:
        """最新のリプライを取得"""
        pass

    @abstractmethod
    def find_replies_excluding_blocked_users(
        self,
        user_id: UserId,
        blocked_user_ids: List[UserId],
        limit: int = 20
    ) -> List[ReplyAggregate]:
        """ブロックしたユーザーのリプライを除外した一覧を取得"""
        pass

    @abstractmethod
    def bulk_delete_replies(self, reply_ids: List[ReplyId], user_id: UserId) -> int:
        """複数のリプライを一括削除（自分のリプライのみ）"""
        pass

    @abstractmethod
    def cleanup_deleted_replies(self, older_than_days: int = 30) -> int:
        """古い削除済みリプライをクリーンアップ"""
        pass

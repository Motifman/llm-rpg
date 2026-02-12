"""
InMemoryReplyRepository - ReplyAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Set, Union
from datetime import datetime, timedelta
from ai_rpg_world.domain.sns.repository.reply_repository import ReplyRepository
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryReplyRepository(ReplyRepository, InMemoryRepositoryBase):
    """ReplyAggregateを使用するインメモリリポジトリ"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _replies(self) -> Dict[ReplyId, ReplyAggregate]:
        return self._data_store.replies

    def generate_reply_id(self) -> ReplyId:
        """新しいリプライIDを生成"""
        reply_id = ReplyId(self._data_store.next_reply_id)
        self._data_store.next_reply_id += 1
        return reply_id

    def save(self, reply: ReplyAggregate) -> None:
        """リプライを保存"""
        cloned_reply = self._clone(reply)
        def operation():
            self._replies[cloned_reply.reply_id] = cloned_reply
            return None
            
        self._register_aggregate(reply)
        return self._execute_operation(operation)

    def find_by_id(self, reply_id: ReplyId) -> Optional[ReplyAggregate]:
        """IDでリプライを取得"""
        return self._replies.get(reply_id)

    def find_by_post_id(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得"""
        replies = [r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_post_id_include_deleted(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得（削除済みを含む）"""
        replies = [r for r in self._replies.values() if r.parent_post_id == post_id]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のユーザーのリプライ一覧を取得"""
        replies = [r for r in self._replies.values() if r.author_user_id == user_id and not r.deleted]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_parent_reply_id(self, parent_reply_id: ReplyId, limit: int = 20) -> List[ReplyAggregate]:
        """特定の親リプライへのリプライ一覧を取得（スレッド表示用）"""
        replies = [r for r in self._replies.values() if r.parent_reply_id == parent_reply_id and not r.deleted]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_mentioning_user(self, user_name: str, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーをメンションしたリプライを取得"""
        replies = []
        for reply in self._replies.values():
            if not reply.deleted and user_name in reply.get_mentioned_users():
                replies.append(reply)
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーがいいねしたリプライ一覧を取得"""
        replies = []
        for reply in self._replies.values():
            if not reply.deleted and reply.is_liked_by_user(user_id):
                replies.append(reply)
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_with_parent_posts(self, limit: int = 20) -> List[tuple]:
        return []

    def search_replies_by_content(self, query: str, limit: int = 20) -> List[ReplyAggregate]:
        """コンテンツでリプライを検索"""
        replies = []
        query_lower = query.lower()
        for reply in self._replies.values():
            if not reply.deleted and query_lower in reply.content.content.lower():
                replies.append(reply)
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def get_reply_count(self, post_id: PostId) -> int:
        """特定のポストへのリプライ数を取得"""
        return len([r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted])

    def find_thread_replies(self, root_post_id: PostId, max_depth: int = 3) -> Dict[Union[PostId, ReplyId], List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用）"""
        result = {}

        def collect_replies(parent_id: Union[PostId, ReplyId], current_depth: int):
            if current_depth > max_depth:
                return

            replies = []
            if isinstance(parent_id, PostId):
                replies = [r for r in self._replies.values() if r.parent_post_id == parent_id and not r.deleted]
            else:
                replies = [r for r in self._replies.values() if r.parent_reply_id == parent_id and not r.deleted]

            replies.sort(key=lambda x: x.created_at)
            result[parent_id] = replies

            for reply in replies:
                collect_replies(reply.reply_id, current_depth + 1)

        collect_replies(root_post_id, 0)
        return result

    def find_thread_replies_include_deleted(self, root_post_id: PostId, max_depth: int = 3) -> Dict[Union[PostId, ReplyId], List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用、削除済みを含む）"""
        result = {}

        def collect_replies(parent_id: Union[PostId, ReplyId], current_depth: int):
            if current_depth > max_depth:
                return

            replies = []
            if isinstance(parent_id, PostId):
                replies = [r for r in self._replies.values() if r.parent_post_id == parent_id]
            else:
                replies = [r for r in self._replies.values() if r.parent_reply_id == parent_id]

            replies.sort(key=lambda x: x.created_at)
            result[parent_id] = replies

            for reply in replies:
                collect_replies(reply.reply_id, current_depth + 1)

        collect_replies(root_post_id, 0)
        return result

    def find_replies_by_post_ids(self, post_ids: List[PostId]) -> Dict[PostId, List[ReplyAggregate]]:
        """複数のポストへのリプライを取得"""
        result = {}
        for post_id in post_ids:
            replies = [r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted]
            replies.sort(key=lambda x: x.created_at, reverse=True)
            result[post_id] = replies
        return result

    def get_user_reply_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーのリプライ統計を取得"""
        user_replies = [r for r in self._replies.values() if r.author_user_id == user_id and not r.deleted]
        total_likes = sum(len(reply.likes) for reply in user_replies)

        return {
            "total_replies": len(user_replies),
            "total_likes_received": total_likes,
            "replies_this_month": len([r for r in user_replies if (datetime.now() - r.created_at).days <= 30])
        }

    def find_recent_replies(self, limit: int = 20) -> List[ReplyAggregate]:
        """最新のリプライを取得"""
        replies = [r for r in self._replies.values() if not r.deleted]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_excluding_blocked_users(
        self,
        user_id: UserId,
        blocked_user_ids: List[UserId],
        limit: int = 20
    ) -> List[ReplyAggregate]:
        replies = [r for r in self._replies.values() if not r.deleted]
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def bulk_delete_replies(self, reply_ids: List[ReplyId], user_id: UserId) -> int:
        """複数のリプライを一括削除（自分のリプライのみ）"""
        def operation():
            deleted_count = 0
            for reply_id in reply_ids:
                reply = self._replies.get(reply_id)
                if reply and reply.author_user_id == user_id and not reply.deleted:
                    reply.delete(user_id, "reply")
                    deleted_count += 1
            return deleted_count
            
        return self._execute_operation(operation)

    def cleanup_deleted_replies(self, older_than_days: int = 30) -> int:
        """古い削除済みリプライをクリーンアップ"""
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        deleted_replies = [r for r in self._replies.values()
                          if r.deleted and r.created_at < cutoff_date]

        for reply in deleted_replies:
            del self._replies[reply.reply_id]

        return len(deleted_replies)

    def find_by_ids(self, entity_ids: List[int]) -> List[ReplyAggregate]:
        """IDのリストでリプライを検索"""
        reply_ids = [ReplyId(rid) for rid in entity_ids]
        return [self._replies.get(rid) for rid in reply_ids if rid in self._replies and not self._replies[rid].deleted]

    def delete(self, entity_id: ReplyId) -> bool:
        """リプライを削除（論理削除）"""
        def operation():
            if entity_id in self._replies:
                reply = self._replies[entity_id]
                if not reply.deleted:
                    reply.delete(reply.author_user_id, "reply")
                    return True
            return False
            
        return self._execute_operation(operation)

    def find_all(self) -> List[ReplyAggregate]:
        """全てのリプライを取得（削除済みは除く）"""
        return [reply for reply in self._replies.values() if not reply.deleted]

    def clear(self) -> None:
        """全てのデータをクリア（テスト用）"""
        self._replies.clear()
        self._data_store.next_reply_id = 1

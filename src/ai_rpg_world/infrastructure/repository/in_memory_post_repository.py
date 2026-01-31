"""
InMemoryPostRepository - PostAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Set
from datetime import datetime, timedelta
from ai_rpg_world.domain.sns.repository.post_repository import PostRepository
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryPostRepository(PostRepository, InMemoryRepositoryBase):
    """PostAggregateを使用するインメモリリポジトリ"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _posts(self) -> Dict[PostId, PostAggregate]:
        return self._data_store.posts

    def find_by_id(self, post_id: int) -> Optional[PostAggregate]:
        """ポストIDでポストを検索"""
        try:
            post_id_obj = PostId(post_id) if not isinstance(post_id, PostId) else post_id
            return self._posts.get(post_id_obj)
        except (ValueError, TypeError):
            return None

    def find_by_ids(self, post_ids: List[PostId]) -> List[PostAggregate]:
        """複数のポストIDでポストを検索"""
        result = []
        for post_id in post_ids:
            post = self._posts.get(post_id)
            if post:
                result.append(post)
        return result

    def save(self, post: PostAggregate) -> PostAggregate:
        """ポストを保存"""
        def operation():
            self._posts[post.post_id] = post
            post.clear_events()  # 発行済みのイベントをクリア
            return post
            
        return self._execute_operation(operation)

    def delete(self, post_id: PostId) -> bool:
        """ポストを削除"""
        def operation():
            if post_id in self._posts:
                del self._posts[post_id]
                return True
            return False
            
        return self._execute_operation(operation)

    def exists_by_id(self, post_id: PostId) -> bool:
        """ポストIDが存在するかチェック"""
        return post_id in self._posts

    def count(self) -> int:
        """ポストの総数を取得"""
        return len(self._posts)

    def find_all(self) -> List[PostAggregate]:
        """全てのポストを取得"""
        return list(self._posts.values())

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """特定のユーザーのポスト一覧を取得（タイムライン用）"""
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]
        # 作成日時の降順でソート
        user_posts.sort(key=lambda p: p.created_at, reverse=True)
        return user_posts[offset:offset + limit]

    def find_by_user_ids(self, user_ids: List[UserId], limit: int = 50, offset: int = 0, sort_by: str = "created_at") -> List[PostAggregate]:
        """複数のユーザーのポストを取得（フォロー中ユーザーの投稿取得用、ソート付き）"""
        result = []
        # 全ての投稿から対象ユーザーのものを抽出（効率は悪いがインメモリなので許容）
        for post in self._posts.values():
            if post.author_user_id in user_ids:
                result.append(post)

        # ソートキーの決定
        if sort_by == "created_at":
            sort_key = lambda p: p.created_at
        else:
            sort_key = lambda p: p.created_at  # デフォルトは作成日時

        # ソート
        result.sort(key=sort_key, reverse=True)

        # offsetとlimitを適用
        return result[offset:offset + limit]

    def find_recent_posts(self, limit: int = 20) -> List[PostAggregate]:
        """最新のポストを取得（トレンド表示用）"""
        all_posts = list(self._posts.values())
        # 作成日時の降順でソート
        all_posts.sort(key=lambda p: p.created_at, reverse=True)
        return all_posts[:limit]

    def find_posts_mentioning_user(self, user_name: str, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーをメンションしたポストを取得"""
        mentioned_posts = []
        for post in self._posts.values():
            if any(mention.mentioned_user_name == user_name for mention in post.mentions):
                mentioned_posts.append(post)

        # 作成日時の降順でソート
        mentioned_posts.sort(key=lambda p: p.created_at, reverse=True)
        return mentioned_posts[:limit]

    def find_liked_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """指定ユーザーがいいねしたポスト一覧を取得"""
        liked_posts = []
        for post in self._posts.values():
            if any(like.user_id == user_id for like in post.likes):
                liked_posts.append(post)

        # いいねした日時の降順でソート（簡易的に作成日時を使用）
        liked_posts.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        return liked_posts[offset:offset + limit]

    def find_posts_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーからいいねされたポスト一覧を取得"""
        return self.find_liked_posts_by_user(user_id, limit)  # 同じ実装でOK

    def search_posts_by_content(self, query: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """コンテンツでポストを検索"""
        result = []
        query_lower = query.lower()
        for post in self._posts.values():
            if query_lower in post.post_content.content.lower():
                result.append(post)

        # 作成日時の降順でソート
        result.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        return result[offset:offset + limit]

    def find_posts_by_hashtag(self, hashtag: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """指定ハッシュタグのポストを取得"""
        result = []
        hashtag_lower = hashtag.lower()
        for post in self._posts.values():
            # ポストのハッシュタグに指定ハッシュタグが含まれているかチェック
            if any(tag.lower() == hashtag_lower for tag in post.post_content.hashtags):
                result.append(post)

        # 作成日時の降順でソート
        result.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        return result[offset:offset + limit]

    def get_like_count(self, post_id: PostId) -> int:
        """特定のポストのいいね数を取得"""
        post = self._posts.get(post_id)
        if post:
            return len(post.likes)
        return 0

    def get_user_post_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの投稿統計（総投稿数、総いいね数など）を取得"""
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]
        total_posts = len(user_posts)
        total_likes = sum(len(post.likes) for post in user_posts)

        return {
            "total_posts": total_posts,
            "total_likes": total_likes
        }

    def find_trending_posts(self, timeframe_hours: int = 24, limit: int = 10, offset: int = 0) -> List[PostAggregate]:
        """トレンドのポストを取得（いいね数やリプライ数でソート）"""
        cutoff_time = datetime.now() - timedelta(hours=timeframe_hours)
        recent_posts = [post for post in self._posts.values() if post.created_at >= cutoff_time]

        # いいね数で降順ソート
        recent_posts.sort(key=lambda p: len(p.likes), reverse=True)

        # offsetとlimitを適用
        return recent_posts[offset:offset + limit]

    def bulk_delete_posts(self, post_ids: List[PostId], user_id: UserId) -> int:
        """複数のポストを一括削除（自分のポストのみ）"""
        def operation():
            deleted_count = 0
            for post_id in post_ids:
                post = self._posts.get(post_id)
                if post and post.author_user_id == user_id:
                    del self._posts[post_id]
                    deleted_count += 1
            return deleted_count
            
        return self._execute_operation(operation)

    def cleanup_deleted_posts(self, older_than_days: int = 30) -> int:
        """古い削除済みポストをクリーンアップ"""
        return 0

    def find_private_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """特定のユーザーのプライベートポストを取得（作成日時降順）"""
        # ユーザーの全てのポストを取得
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]

        # プライベートポストのみをフィルタリング
        private_posts = [post for post in user_posts if post.is_private()]

        # 作成日時の降順でソート
        private_posts.sort(key=lambda p: p.get_sort_key_by_created_at(), reverse=True)

        # offsetとlimitを適用
        return private_posts[offset:offset + limit]

    def clear(self) -> None:
        """全てのポストを削除（テスト用）"""
        self._posts.clear()
        self._data_store.next_post_id = 1

    def find_posts_in_timeframe(self, timeframe_hours: int = 24, limit: int = 1000) -> List[PostAggregate]:
        """指定時間内の全ポストを取得（トレンド計算用）"""
        cutoff_time = datetime.now() - timedelta(hours=timeframe_hours)
        recent_posts = [post for post in self._posts.values() if post.created_at >= cutoff_time]
        return recent_posts[:limit]

    def generate_post_id(self) -> PostId:
        """ポストIDを生成"""
        post_id = PostId(self._data_store.next_post_id)
        self._data_store.next_post_id += 1
        return post_id

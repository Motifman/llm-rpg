import itertools
from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.aggregate import PostAggregate
from ai_rpg_world.domain.sns.repository.post_repository import PostRepository
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, UserId


class _TestPostRepositoryInterface:
    """PostRepositoryインターフェースのテスト基幹クラス"""

    @pytest.fixture
    def repository(self) -> PostRepository:
        """具象実装を返すfixture - サブクラスでオーバーライド"""
        raise NotImplementedError("サブクラスで実装してください")

    def test_find_by_id_existing_post(self, repository):
        """既存ポストのID検索テスト"""
        post = repository.find_by_id(PostId(1))
        assert post is not None
        assert post.post_id == PostId(1)
        assert post.author_user_id == UserId(1)

    def test_find_by_id_nonexistent_post(self, repository):
        """存在しないポストのID検索テスト"""
        post = repository.find_by_id(PostId(999))
        assert post is None

    def test_find_by_ids_multiple_posts(self, repository):
        """複数ポストのID検索テスト"""
        posts = repository.find_by_ids([PostId(1), PostId(2)])
        assert len(posts) == 2
        post_ids = [post.post_id for post in posts]
        assert set(post_ids) == {PostId(1), PostId(2)}

    def test_find_by_user_id(self, repository):
        """ユーザーIDによるポスト検索テスト"""
        posts = repository.find_by_user_id(UserId(1), limit=10)
        assert isinstance(posts, list)
        assert len(posts) >= 1
        for post in posts:
            assert post.author_user_id == UserId(1)

    def test_find_by_user_ids_multiple_users(self, repository):
        """複数ユーザーIDによるポスト検索テスト"""
        posts = repository.find_by_user_ids([UserId(1), UserId(2)], limit=10)
        assert isinstance(posts, list)
        user_ids = set(post.author_user_id for post in posts)
        assert user_ids.issubset({UserId(1), UserId(2)})

    def test_find_by_user_ids_orders_by_created_at_descending(self, repository):
        """find_by_user_ids は作成日時の降順で返す。"""
        posts = repository.find_by_user_ids([UserId(1), UserId(2)], limit=50)
        assert len(posts) > 1
        for newer, older in itertools.pairwise(posts):
            assert newer.created_at >= older.created_at

    def test_find_by_user_ids_breaks_created_at_ties_by_post_id_descending(self, repository):
        """find_by_user_ids は作成日時が同じポストを post_id の降順で返す。"""
        same_time = datetime(2026, 1, 1, 0, 0, 0)
        for post_id in (101, 102, 103):
            repository.save(
                PostAggregate(
                    PostId(post_id),
                    UserId(1),
                    PostContent(content=f"同時刻のポスト {post_id}"),
                    set(),
                    set(),
                    set(),
                    False,
                    None,
                    None,
                    same_time,
                )
            )

        posts = repository.find_by_user_ids([UserId(1)], limit=50)
        tied_post_ids = [post.post_id for post in posts if post.created_at == same_time]
        assert tied_post_ids == [PostId(103), PostId(102), PostId(101)]

    def test_find_recent_posts(self, repository):
        """最新ポスト取得テスト"""
        posts = repository.find_recent_posts(limit=5)
        assert isinstance(posts, list)
        assert len(posts) <= 5
        # 時系列でソートされていることを確認（新しい順）
        if len(posts) > 1:
            for i in range(len(posts) - 1):
                assert posts[i].created_at >= posts[i + 1].created_at

    def test_find_posts_by_hashtag(self, repository):
        """ハッシュタグによるポスト検索テスト"""
        posts = repository.find_posts_by_hashtag("冒険", limit=10)
        assert isinstance(posts, list)
        for post in posts:
            assert "冒険" in post.content.hashtags

    def test_find_posts_mentioning_user(self, repository):
        """メンションによるポスト検索テスト"""
        posts = repository.find_posts_mentioning_user("hero_user", limit=10)
        assert isinstance(posts, list)
        # メンションされたポストがあることを確認

    def test_search_posts_by_content(self, repository):
        """コンテンツによるポスト検索テスト"""
        posts = repository.search_posts_by_content("魔法", limit=10)
        assert isinstance(posts, list)
        for post in posts:
            assert "魔法" in post.content.content

    def test_generate_post_id(self, repository):
        """ポストID生成テスト"""
        post_id = repository.generate_post_id()
        assert isinstance(post_id, PostId)
        assert post_id.value >= 6  # サンプルデータで5つのポストがあるので6以上

    def test_exists_by_id(self, repository):
        """ポスト存在確認テスト"""
        assert repository.exists_by_id(PostId(1)) == True
        assert repository.exists_by_id(PostId(999)) == False

    def test_count(self, repository):
        """総ポスト数取得テスト"""
        count = repository.count()
        assert count >= 5  # サンプルデータで少なくとも5つのポスト

    def test_find_all(self, repository):
        """全ポスト取得テスト"""
        posts = repository.find_all()
        assert len(posts) >= 5  # サンプルデータで少なくとも5つのポスト
        post_ids = [post.post_id for post in posts]
        # 少なくともサンプルデータのポストIDが含まれていることを確認
        expected_ids = {PostId(1), PostId(2), PostId(3), PostId(4), PostId(5)}
        assert expected_ids.issubset(set(post_ids))

import pytest
from typing import List
from src.domain.sns.repository.reply_repository import ReplyRepository
from src.domain.sns.value_object import UserId, PostId, ReplyId


class _TestReplyRepositoryInterface:
    """ReplyRepositoryインターフェースのテスト基幹クラス"""

    @pytest.fixture
    def repository(self) -> ReplyRepository:
        """具象実装を返すfixture - サブクラスでオーバーライド"""
        raise NotImplementedError("サブクラスで実装してください")

    def test_find_by_id_existing_reply(self, repository):
        """既存リプライのID検索テスト"""
        from src.domain.sns.value_object import ReplyId, UserId
        reply = repository.find_by_id(ReplyId(1))
        assert reply is not None
        assert reply.reply_id == ReplyId(1)
        assert reply.author_user_id == UserId(2)

    def test_find_by_id_nonexistent_reply(self, repository):
        """存在しないリプライのID検索テスト"""
        from src.domain.sns.value_object import ReplyId
        reply = repository.find_by_id(ReplyId(999))
        assert reply is None

    def test_find_by_ids_multiple_replies(self, repository):
        """複数リプライのID検索テスト"""
        from src.domain.sns.value_object import ReplyId
        replies = repository.find_by_ids([1, 2])  # InMemory実装はList[int]を受け取る
        assert len(replies) == 2
        reply_ids = [reply.reply_id for reply in replies]
        assert set(reply_ids) == {ReplyId(1), ReplyId(2)}

    def test_find_by_post_id(self, repository):
        """ポストIDによるリプライ検索テスト"""
        from src.domain.sns.value_object import PostId
        replies = repository.find_by_post_id(PostId(1), limit=10)
        assert isinstance(replies, List)
        for reply in replies:
            assert reply.parent_post_id == PostId(1)

    def test_find_by_post_id_include_deleted(self, repository):
        """ポストIDによるリプライ検索テスト（削除済みを含む）"""
        from src.domain.sns.value_object import PostId
        replies = repository.find_by_post_id_include_deleted(PostId(1), limit=10)
        assert isinstance(replies, List)
        for reply in replies:
            assert reply.parent_post_id == PostId(1)

    def test_find_by_user_id(self, repository):
        """ユーザーIDによるリプライ検索テスト"""
        from src.domain.sns.value_object import UserId
        replies = repository.find_by_user_id(UserId(1), limit=10)
        assert isinstance(replies, List)
        for reply in replies:
            assert reply.author_user_id == UserId(1)

    def test_find_by_parent_reply_id(self, repository):
        """親リプライIDによるリプライ検索テスト"""
        from src.domain.sns.value_object import ReplyId
        replies = repository.find_by_parent_reply_id(ReplyId(3), limit=10)
        assert isinstance(replies, List)
        for reply in replies:
            assert reply.parent_reply_id == ReplyId(3)

    def test_find_replies_mentioning_user(self, repository):
        """メンションによるリプライ検索テスト"""
        replies = repository.find_replies_mentioning_user("hero_user", limit=10)
        assert isinstance(replies, List)
        # メンションされたリプライがあることを確認

    def test_search_replies_by_content(self, repository):
        """コンテンツによるリプライ検索テスト"""
        replies = repository.search_replies_by_content("魔法", limit=10)
        assert isinstance(replies, List)
        for reply in replies:
            assert "魔法" in reply.content.content


    def test_generate_reply_id(self, repository):
        """リプライID生成テスト"""
        from src.domain.sns.value_object import ReplyId
        reply_id = repository.generate_reply_id()
        assert isinstance(reply_id, ReplyId)
        assert reply_id.value >= 8  # サンプルデータで7つのリプライがあるので8以上

    def test_find_all(self, repository):
        """全リプライ取得テスト"""
        from src.domain.sns.value_object import ReplyId
        replies = repository.find_all()
        assert len(replies) >= 7  # サンプルデータで少なくとも7つのリプライ
        reply_ids = [reply.reply_id for reply in replies]
        # 少なくともサンプルデータのReplyIDが含まれていることを確認
        expected_ids = {ReplyId(1), ReplyId(2), ReplyId(3), ReplyId(4), ReplyId(5), ReplyId(6), ReplyId(7)}
        assert expected_ids.issubset(set(reply_ids))

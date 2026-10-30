import pytest

from ai_rpg_world.domain.sns.exception import MentionValidationException
from ai_rpg_world.domain.sns.value_object import Mention, PostId, ReplyId


class TestMention:
    """Mentionバリューオブジェクトのテスト"""

    @pytest.mark.parametrize("post_id", [PostId(1), PostId(999999), PostId(123), ReplyId(1)])
    def test_create_mention_success(self, post_id):
        """表示名と、小さい値・大きい値・返信を含む型付き対象IDをそのまま保持する。"""
        mention = Mention("testuser", post_id)

        assert mention.mentioned_user_name == "testuser"
        assert mention.post_id == post_id

    def test_none_mentioned_user_name_handling(self):
        """mentioned_user_nameがNoneの場合の動作テスト"""
        # Noneを渡してもdataclassesは型チェックを強制しないため、動作する
        mention = Mention(None, PostId(1))
        assert mention.mentioned_user_name is None
        assert mention.post_id == PostId(1)

    def test_empty_mentioned_user_name_raises_error(self):
        """mentioned_user_nameが空文字の場合のエラーテスト"""
        with pytest.raises(MentionValidationException, match="メンションするユーザー名は必須です"):
            Mention("", PostId(1))

    def test_various_mentioned_user_names(self):
        """様々なユーザー名のテスト"""
        post_id = PostId(1)

        # 通常のユーザー名
        mention1 = Mention("testuser", post_id)
        assert mention1.mentioned_user_name == "testuser"

        # 長いユーザー名
        long_username = "a" * 50
        mention2 = Mention(long_username, post_id)
        assert mention2.mentioned_user_name == long_username

        # 特殊文字を含むユーザー名
        special_username = "test_user-123"
        mention3 = Mention(special_username, post_id)
        assert mention3.mentioned_user_name == special_username

    @pytest.mark.parametrize("content_id_type", [PostId, ReplyId], ids=["post", "reply"])
    def test_equality_comparison(self, content_id_type):
        """同じ表示名と型付き対象IDの別個体は、集合で重複せず相互に検索・除去できる。"""
        mention1 = Mention("testuser", content_id_type(1))
        mention2 = Mention("testuser", content_id_type(1))

        assert mention1 == mention2
        assert hash(mention1) == hash(mention2)
        mentions = {mention1, mention2}
        assert len(mentions) == 1
        assert mention2 in mentions
        mentions.remove(mention2)
        assert mentions == set()

    @pytest.mark.parametrize(
        ("first_name", "second_name"),
        [("testuser1", "testuser2"), ("testuser", "otheruser")],
    )
    def test_inequality_with_different_mentioned_user_names(self, first_name, second_name):
        """対象IDが同じでも表示名が違えば、別のメンションとして集合に共存する。"""
        mention1 = Mention(first_name, PostId(1))
        mention2 = Mention(second_name, PostId(1))

        assert mention1 != mention2
        assert len({mention1, mention2}) == 2

    @pytest.mark.parametrize(
        ("first_id", "second_id"),
        [(PostId(1), PostId(2)), (ReplyId(1), ReplyId(2)), (PostId(1), ReplyId(1))],
        ids=["post-value", "reply-value", "target-kind"],
    )
    def test_inequality_with_different_post_ids(self, first_id, second_id):
        """表示名が同じでも対象の値か型が違えば、別のメンションとして集合に共存する。"""
        mention1 = Mention("testuser", first_id)
        mention2 = Mention("testuser", second_id)

        assert mention1 != mention2
        assert len({mention1, mention2}) == 2

    @pytest.mark.parametrize(
        ("attribute", "replacement"),
        [("mentioned_user_name", "otheruser"), ("post_id", PostId(2))],
    )
    def test_immutability(self, attribute, replacement):
        """表示名と対象IDの再代入を拒み、構築時の両方の値を保持する。"""
        mention = Mention("testuser", PostId(1))

        with pytest.raises(AttributeError):
            setattr(mention, attribute, replacement)

        assert mention.mentioned_user_name == "testuser"
        assert mention.post_id == PostId(1)

        # 作成後に変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_edge_cases_for_mentioned_user_name(self):
        """ユーザー名のエッジケーステスト"""
        post_id = PostId(1)

        # スペースを含むユーザー名
        mention1 = Mention("test user", post_id)
        assert mention1.mentioned_user_name == "test user"

        # 数字のみのユーザー名
        mention2 = Mention("12345", post_id)
        assert mention2.mentioned_user_name == "12345"

        # 記号を含むユーザー名
        mention3 = Mention("test@user", post_id)
        assert mention3.mentioned_user_name == "test@user"

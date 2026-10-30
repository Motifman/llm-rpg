from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.value_object import Like, PostId, ReplyId, UserId


class TestLike:
    """Likeバリューオブジェクトのテスト"""

    @pytest.mark.parametrize(
        ("user_id", "post_id", "check_original_conversion"),
        [
            (UserId(1), PostId(1), False),
            (UserId(999999), PostId(999999), False),
            (UserId(123), PostId(456), True),
            (UserId(123), ReplyId(456), False),
        ],
        ids=["minimum", "large", "distinct-ids", "reply"],
    )
    def test_create_like_success(self, user_id, post_id, check_original_conversion):
        """大小の実行者IDと型付き対象IDを保持し、省略した作成時刻を生成する。"""
        like = Like(user_id, post_id)

        assert like.user_id == user_id
        assert like.post_id == post_id
        assert isinstance(like.created_at, datetime)
        if check_original_conversion:
            assert str(like.user_id) == "123"
            assert str(like.post_id) == "456"
            assert int(like.user_id) == 123
            assert int(like.post_id) == 456

    def test_create_like_with_explicit_datetime(self):
        """明示的な日時でのLike作成テスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like = Like(user_id, post_id, specific_time)

        assert like.user_id == user_id
        assert like.post_id == post_id
        assert like.created_at == specific_time

    @pytest.mark.parametrize(
        ("content_id_type", "other_content_id_type"),
        [(PostId, ReplyId), (ReplyId, PostId)],
        ids=["post", "reply"],
    )
    def test_hash_functionality(self, content_id_type, other_content_id_type):
        """同値のいいねを重複させず、実行者・対象の値と型が違えば集合で区別する。"""
        specific_time = datetime(2023, 1, 1, 12, 0, 0)
        like1 = Like(UserId(1), content_id_type(1), specific_time)
        like2 = Like(UserId(1), content_id_type(1), specific_time)
        different_user = Like(UserId(2), content_id_type(1), specific_time)
        different_target = Like(UserId(1), content_id_type(2), specific_time)
        other_kind = Like(UserId(1), other_content_id_type(1), specific_time)

        assert like1 == like2
        assert hash(like1) == hash(like2)
        assert like1 != different_user
        assert like1 != different_target
        assert like1 != other_kind

        likes = {like1, like2, different_user, different_target, other_kind}
        assert len(likes) == 4
        assert like2 in likes
        likes.remove(like2)
        assert like1 not in likes
        assert likes == {different_user, different_target, other_kind}

    def test_hash_with_different_creation_times(self):
        """異なる作成時間のハッシュテスト"""
        user_id = UserId(1)
        post_id = PostId(1)
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)

        like1 = Like(user_id, post_id, time1)
        like2 = Like(user_id, post_id, time2)

        # 同じIDでも異なる時間の場合は等価（作成時間は比較に含めない）
        assert like1 == like2
        assert hash(like1) == hash(like2)

    @pytest.mark.parametrize(
        ("attribute", "replacement"),
        [
            ("user_id", UserId(2)),
            ("post_id", PostId(2)),
            ("created_at", datetime(2023, 1, 2, 12, 0, 0)),
        ],
    )
    def test_immutability(self, attribute, replacement):
        """実行者・対象・時刻の再代入を拒み、構築時の全値を保持する。"""
        like = Like(UserId(1), PostId(1), datetime(2023, 1, 1, 12, 0, 0))

        with pytest.raises(AttributeError):
            setattr(like, attribute, replacement)

        assert like.user_id == UserId(1)
        assert like.post_id == PostId(1)
        assert like.created_at == datetime(2023, 1, 1, 12, 0, 0)

        # 作成後にプロパティを変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_created_at_auto_generation(self):
        """時刻を省略したいいねには、構築前後の時刻の間に生成した日時が入る。"""
        before = datetime.now()
        like = Like(UserId(1), PostId(1))
        after = datetime.now()

        assert before <= like.created_at <= after

"""公開参照の識別子は整数の採番や表示状態と独立して保持される。"""

from copy import deepcopy
from uuid import UUID

import pytest

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.exception.identity_token_exception import SnsIdentityValidationException
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.domain.sns.value_object.sns_identity_token import SnsIdentityToken


def _create(kind: str):
    if kind == "post":
        return PostAggregate.create(PostId(1), UserId(1), PostContent("同じ投稿"))
    return ReplyAggregate.create(
        ReplyId(1), PostId(1), None, UserId(1), UserId(2), PostContent("同じ返信")
    )


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_new_content_with_reused_integer_has_distinct_identity(kind: str) -> None:
    """整数と本文が同一でも、新しく作った投稿や返信には異なる UUID4 を割り当てる。"""
    first, second = _create(kind), _create(kind)
    assert first.content_id == second.content_id
    assert UUID(hex=first.identity_token).version == 4
    assert UUID(hex=first.identity_token).hex == first.identity_token
    assert first.identity_token != second.identity_token


@pytest.mark.parametrize("kind", ["post", "reply"])
def test_identity_is_read_only_and_survives_copy_and_deletion(kind: str) -> None:
    """複製・いいね・削除は識別子を変えず、公開プロパティからの置換も認めない。"""
    content = _create(kind)
    token = content.identity_token
    clone = deepcopy(content)
    clone.like(UserId(3), kind)
    clone.delete(clone.author_user_id, kind)
    assert clone.identity_token == token
    with pytest.raises(AttributeError):
        clone.identity_token = "f" * 32


@pytest.mark.parametrize("token", ["", "post_1", "F" * 32, "0" * 32])
def test_restoration_rejects_invalid_identity(token: str) -> None:
    """復元識別子が正規形の UUID4 でないとき、新規発行せずドメイン例外で止める。"""
    with pytest.raises(SnsIdentityValidationException):
        PostAggregate.create_from_db(
            PostId(1), UserId(1), PostContent("本文"), set(), set(), set(),
            identity_token=token,
        )


def test_user_identity_does_not_depend_on_name_or_integer() -> None:
    """同名で同じ整数を割り当てた別の利用者も、不変識別子で区別できる。"""
    first = UserAggregate.create_new_user(UserId(1), "hero", "勇者", "")
    second = UserAggregate.create_new_user(UserId(1), "hero", "勇者", "")
    assert first.identity_token != second.identity_token
    assert deepcopy(first).identity_token == first.identity_token
    with pytest.raises(AttributeError):
        first.identity_token = second.identity_token


def test_identity_value_object_is_immutable() -> None:
    """識別子の値オブジェクトは値の書き換えを許さない。"""
    token = SnsIdentityToken()
    with pytest.raises(AttributeError):
        token.value = SnsIdentityToken().value

"""SNS 画面を入り直しても古い参照が別の対象へ化けないことを保証する。"""

import pytest

from ai_rpg_world.application.social.sns_virtual_pages import SnsPageSessionService


@pytest.mark.parametrize("kind", ["post", "user", "reply", "notification"])
@pytest.mark.parametrize("exit_first", [False, True])
def test_enter_does_not_recycle_old_ref(kind: str, exit_first: bool) -> None:
    """再入室前の参照は無効のままで、新しい対象の参照として再利用されない。"""
    session = SnsPageSessionService()
    session.on_enter_sns(1)
    issue = getattr(session, f"issue_{kind}_ref")
    resolve = getattr(session, f"resolve_{kind}_ref")
    old_ref = issue(1, 10)
    if exit_first:
        session.on_exit_sns(1)
    session.on_enter_sns(1)
    new_ref = issue(1, 20)
    assert resolve(1, old_ref) is None
    assert resolve(1, new_ref) == 20
    assert old_ref != new_ref


@pytest.mark.parametrize("kind", ["post", "user", "reply", "notification"])
def test_refs_cannot_be_used_by_another_player(kind: str) -> None:
    """別のプレイヤーに発行した参照では、自分の同種の対象も操作できない。"""
    session = SnsPageSessionService()
    issue = getattr(session, f"issue_{kind}_ref")
    resolve = getattr(session, f"resolve_{kind}_ref")
    first_ref = issue(1, 10)
    second_ref = issue(2, 20)
    assert resolve(2, first_ref) is None
    assert resolve(1, second_ref) is None
    assert resolve(1, first_ref) == 10
    assert resolve(2, second_ref) == 20


def test_refresh_does_not_recycle_old_ref() -> None:
    """画面更新の前に発行した参照は、新しい行の発行後も無効のままである。"""
    session = SnsPageSessionService()
    old_ref = session.issue_post_ref(1, 10)
    session.bump_snapshot_generation(1)
    new_ref = session.issue_post_ref(1, 20)
    assert session.resolve_post_ref(1, old_ref) is None
    assert session.resolve_post_ref(1, new_ref) == 20


@pytest.mark.parametrize("kind", ["post", "user", "reply", "notification"])
def test_recreated_service_does_not_accept_refs_from_previous_runtime(kind: str) -> None:
    """履歴から復元された過去の参照は、新しく作った実行環境の対象を指さない。"""
    previous = SnsPageSessionService()
    old_ref = getattr(previous, f"issue_{kind}_ref")(1, 10)
    resumed = SnsPageSessionService()
    new_ref = getattr(resumed, f"issue_{kind}_ref")(1, 20)
    resolve = getattr(resumed, f"resolve_{kind}_ref")
    assert resolve(1, old_ref) is None
    assert resolve(1, new_ref) == 20
    assert old_ref != new_ref

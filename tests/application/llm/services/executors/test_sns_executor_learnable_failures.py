"""Issue #168 PR-5: ``SnsToolExecutor`` の bare failure DTO を learnable に
統一する。

PR #170 で enter の ``ActiveGameAppConflictError`` サニタイズは対応済み。
本 PR は **page/ref 系の失敗** に error_code + remediation を必ず付けるよう
ガードする。

主な error_code:
- ``SNS_REF_STALE``: post_ref / reply_ref / notification_ref / target_user_ref /
  profile_user_ref が解決できない、リプライ/通知が見つからない 等
- ``SNS_PAGE_NOT_SUPPORTED``: 「未対応の画面です」「home でのみタブ切替」
  「通知から遷移できない」 等
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.sns_executor import (
    SnsToolExecutor,
)


def _build_executor(*, sns_page_session=None) -> SnsToolExecutor:
    return SnsToolExecutor(
        sns_mode_session=MagicMock(),
        sns_page_session=sns_page_session,
    )


def _stale_ref_session() -> MagicMock:
    """全 resolve_*_ref が None を返す sns_page_session。"""
    sess = MagicMock()
    sess.resolve_post_ref.return_value = None
    sess.resolve_reply_ref.return_value = None
    sess.resolve_notification_ref.return_value = None
    sess.resolve_user_ref.return_value = None
    return sess


def _assert_learnable(result, expected_error_code: str) -> None:
    assert result.success is False
    assert result.error_code == expected_error_code, (
        f"expected {expected_error_code}, got {result.error_code!r}: {result.message!r}"
    )
    assert result.remediation


class TestResolveRefStaleness:
    """``_resolve_*_ref_from_args`` の stale ref 失敗。"""

    def test_post_ref_stale_is_learnable(self) -> None:
        executor = _build_executor(sns_page_session=_stale_ref_session())
        _post_id, err = executor._resolve_post_id_from_args(
            player_id=1, args={"post_ref": "stale-1"}
        )
        assert err is not None
        _assert_learnable(err, "SNS_REF_STALE")

    def test_reply_ref_stale_is_learnable(self) -> None:
        executor = _build_executor(sns_page_session=_stale_ref_session())
        _reply_id, err = executor._resolve_reply_id_from_args(
            player_id=1, args={"reply_ref": "stale-r"}
        )
        assert err is not None
        _assert_learnable(err, "SNS_REF_STALE")

    def test_notification_ref_stale_is_learnable(self) -> None:
        executor = _build_executor(sns_page_session=_stale_ref_session())
        _nid, err = executor._resolve_notification_id_from_args(
            player_id=1, args={"notification_ref": "stale-n"}
        )
        assert err is not None
        _assert_learnable(err, "SNS_REF_STALE")

    def test_target_user_ref_stale_is_learnable(self) -> None:
        executor = _build_executor(sns_page_session=_stale_ref_session())
        _uid, err = executor._resolve_target_user_id_from_args(
            player_id=1, args={"target_user_ref": "stale-u"}
        )
        assert err is not None
        _assert_learnable(err, "SNS_REF_STALE")


class TestOpenPageRefStaleness:
    """``_execute_open_page`` の ref 解決失敗。"""

    def test_post_detail_with_stale_ref_is_learnable(self) -> None:
        sess = _stale_ref_session()
        executor = SnsToolExecutor(
            sns_mode_session=MagicMock(),
            sns_page_session=sess,
            sns_page_query_service=MagicMock(),
        )
        result = executor._execute_open_page(
            player_id=1,
            args={"page": "post_detail", "post_ref": "stale-1"},
        )
        _assert_learnable(result, "SNS_REF_STALE")

    def test_profile_with_stale_ref_is_learnable(self) -> None:
        sess = _stale_ref_session()
        executor = SnsToolExecutor(
            sns_mode_session=MagicMock(),
            sns_page_session=sess,
            sns_page_query_service=MagicMock(),
        )
        result = executor._execute_open_page(
            player_id=1,
            args={"page": "profile", "profile_user_ref": "stale-u"},
        )
        _assert_learnable(result, "SNS_REF_STALE")


class TestOpenRefResolution:
    """``_execute_open_ref`` の全 resolve 経路が無効な ref の場合。"""

    def test_unresolved_ref_yields_sns_ref_stale(self) -> None:
        sess = _stale_ref_session()
        executor = SnsToolExecutor(
            sns_mode_session=MagicMock(),
            sns_page_session=sess,
            sns_page_query_service=MagicMock(),
        )
        result = executor._execute_open_ref(
            player_id=1, args={"ref": "nonexistent"}
        )
        _assert_learnable(result, "SNS_REF_STALE")


class TestSwitchTabPageRestriction:
    """``_execute_switch_tab`` は home 以外では使えない。"""

    def test_switch_tab_off_home_is_learnable(self) -> None:
        from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
            SnsVirtualPageKind,
        )

        sess = MagicMock()
        sess.get_state.return_value = MagicMock(
            page_kind=SnsVirtualPageKind.PROFILE
        )
        executor = SnsToolExecutor(
            sns_mode_session=MagicMock(),
            sns_page_session=sess,
        )
        result = executor._execute_switch_tab(
            player_id=1, args={"tab": "FOLLOWING"}
        )
        _assert_learnable(result, "SNS_PAGE_NOT_SUPPORTED")


class TestAllFailuresHaveLearnableShape:
    """ファイル走査による不変条件 — bare `success=False` が残っていない。

    ``LlmCommandResultDto(success=False, ...)`` の全箇所が error_code を
    持つことを静的にチェックする。将来の追加で error_code 漏れが起きないよう
    回帰防止する。
    """

    def test_no_bare_failure_in_sns_executor_source(self) -> None:
        import re
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[5]
            / "src"
            / "ai_rpg_world"
            / "application"
            / "llm"
            / "services"
            / "executors"
            / "sns_executor.py"
        ).read_text(encoding="utf-8")
        # success=False の出現位置の次の 10 行以内に error_code= が必ず有ること
        for m in re.finditer(r"success=False", src):
            window = src[m.start(): m.start() + 600]
            assert "error_code" in window, (
                f"bare success=False at pos {m.start()}: {window[:200]!r}"
            )

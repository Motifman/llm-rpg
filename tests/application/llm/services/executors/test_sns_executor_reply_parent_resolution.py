"""SnsToolExecutor: sns_create_reply の親 (ポスト / リプライ) 特定の単体テスト。"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.sns_executor import SnsToolExecutor
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SNS_CREATE_REPLY
from ai_rpg_world.application.social.contracts.dtos import CommandResultDto
from ai_rpg_world.application.social.sns_virtual_pages import SnsPageSessionService


@pytest.fixture
def page_session() -> SnsPageSessionService:
    return SnsPageSessionService()


@pytest.fixture
def reply_service() -> MagicMock:
    service = MagicMock()
    service.create_reply = MagicMock(
        return_value=CommandResultDto(success=True, message="リプライを作成しました。")
    )
    return service


def _handler(
    reply_service: MagicMock, page_session: SnsPageSessionService
) -> Any:
    executor = SnsToolExecutor(
        reply_service=reply_service,
        sns_page_session=page_session,
    )
    return executor.get_handlers()[TOOL_NAME_SNS_CREATE_REPLY]


class TestReplyParentResolution:
    """sns_create_reply が親を 1 つだけ受け取ることを保証する。"""

    def test_parent_post_ref_alone_passes_post_id_to_the_command(
        self, reply_service: MagicMock, page_session: SnsPageSessionService
    ) -> None:
        """parent_post_ref だけを渡すと、command の parent_post_id にその ID が入り parent_reply_id は None になる。"""
        page_session.issue_post_ref(1, 7)
        ref = next(iter(page_session.get_state(1).ref_to_post_id.keys()))

        result = _handler(reply_service, page_session)(
            1, {"content": "やあ", "parent_post_ref": ref}
        )

        assert result.success
        command = reply_service.create_reply.call_args.args[0]
        assert command.parent_post_id == 7
        assert command.parent_reply_id is None

    def test_parent_reply_ref_alone_passes_reply_id_to_the_command(
        self, reply_service: MagicMock, page_session: SnsPageSessionService
    ) -> None:
        """parent_reply_ref だけを渡すと、command の parent_reply_id にその ID が入り parent_post_id は None になる。"""
        page_session.issue_reply_ref(1, 9)
        ref = next(iter(page_session.get_state(1).ref_to_reply_id.keys()))

        result = _handler(reply_service, page_session)(
            1, {"content": "やあ", "parent_reply_ref": ref}
        )

        assert result.success
        command = reply_service.create_reply.call_args.args[0]
        assert command.parent_post_id is None
        assert command.parent_reply_id == 9

    def test_both_parent_refs_fail_without_calling_the_service(
        self, reply_service: MagicMock, page_session: SnsPageSessionService
    ) -> None:
        """parent_post_ref と parent_reply_ref を両方渡すと失敗し、リプライは作成されない。"""
        page_session.issue_post_ref(1, 7)
        page_session.issue_reply_ref(1, 9)
        state = page_session.get_state(1)
        post_ref = next(iter(state.ref_to_post_id.keys()))
        reply_ref = next(iter(state.ref_to_reply_id.keys()))

        result = _handler(reply_service, page_session)(
            1,
            {"content": "やあ", "parent_post_ref": post_ref, "parent_reply_ref": reply_ref},
        )

        assert not result.success
        reply_service.create_reply.assert_not_called()

    def test_both_parent_ids_fail_without_calling_the_service(
        self, reply_service: MagicMock, page_session: SnsPageSessionService
    ) -> None:
        """parent_post_id と parent_reply_id を両方渡すと失敗し、リプライは作成されない。"""
        result = _handler(reply_service, page_session)(
            1, {"content": "やあ", "parent_post_id": 7, "parent_reply_id": 9}
        )

        assert not result.success
        reply_service.create_reply.assert_not_called()

    def test_no_parent_at_all_fails_without_calling_the_service(
        self, reply_service: MagicMock, page_session: SnsPageSessionService
    ) -> None:
        """親をひとつも渡さないと失敗し、リプライは作成されない。"""
        result = _handler(reply_service, page_session)(1, {"content": "やあ"})

        assert not result.success
        reply_service.create_reply.assert_not_called()

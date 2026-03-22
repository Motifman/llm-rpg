"""Phase 6: 軽量 read projection は採用しないことの回帰テスト。

未読数は NotificationQueryService 経由のライブ集計、ref 無効化は
SnsPageSessionService のスナップショット世代で足りる（PLAN Phase 6 確定）。
"""

from unittest.mock import MagicMock

from ai_rpg_world.application.social.sns_virtual_pages.kinds import SnsVirtualPageKind
from ai_rpg_world.application.social.sns_virtual_pages.sns_page_query_service import (
    SnsPageQueryService,
)
from ai_rpg_world.application.social.sns_virtual_pages.sns_page_session_service import (
    SnsPageSessionService,
)


def test_notifications_unread_uses_notification_query_live_aggregate() -> None:
    """未読数は別 projection ストアではなく NotificationQueryService.get_unread_count に集約される。"""
    session = SnsPageSessionService()
    nq = MagicMock()
    nq.get_user_notifications.return_value = []
    nq.get_unread_count.return_value = 42
    svc = SnsPageQueryService(MagicMock(), MagicMock(), nq, MagicMock(), session)
    session.on_enter_sns(1)
    session.get_state(1).page_kind = SnsVirtualPageKind.NOTIFICATIONS
    snap = svc.get_current_page_snapshot(1, viewer_user_id=1)
    assert snap.notifications is not None
    assert snap.notifications.unread_count == 42
    nq.get_unread_count.assert_called_once_with(1)

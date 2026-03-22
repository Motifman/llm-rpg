"""SNS 仮想画面の page session 状態（メモリ上・プレイヤー単位）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
    SnsHomeTab,
    SnsSearchMode,
    SnsVirtualPageKind,
)

_DEFAULT_PAGE_LIMIT = 20
_MAX_PAGE_LIMIT = 100


def clamp_page_limit(limit: Optional[int]) -> int:
    """limit 省略時は 20、最大 100 に収める。"""
    if limit is None:
        return _DEFAULT_PAGE_LIMIT
    return max(1, min(int(limit), _MAX_PAGE_LIMIT))


@dataclass
class SnsPageSessionState:
    """現在画面・タブ・ページング・検索条件・ref マップ・スナップショット世代を保持する。"""

    page_kind: SnsVirtualPageKind = SnsVirtualPageKind.HOME
    home_tab: SnsHomeTab = SnsHomeTab.FOLLOWING
    limit: int = _DEFAULT_PAGE_LIMIT
    offset: int = 0
    search_mode: Optional[SnsSearchMode] = None
    search_query: str = ""
    profile_target_user_id: Optional[int] = None
    post_detail_root_post_id: Optional[int] = None
    snapshot_generation: int = 0
    ref_seq: int = 0
    ref_to_post_id: Dict[str, int] = field(default_factory=dict)
    ref_to_user_id: Dict[str, int] = field(default_factory=dict)
    ref_to_reply_id: Dict[str, int] = field(default_factory=dict)
    ref_to_notification_id: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def default_home(cls) -> SnsPageSessionState:
        """SNS 入室直後: home / following。"""
        return cls(
            page_kind=SnsVirtualPageKind.HOME,
            home_tab=SnsHomeTab.FOLLOWING,
            limit=_DEFAULT_PAGE_LIMIT,
            offset=0,
        )

    def clear_ref_maps(self) -> None:
        """同一世代内の ref を破棄（世代更新時に呼ぶ）。"""
        self.ref_to_post_id.clear()
        self.ref_to_user_id.clear()
        self.ref_to_reply_id.clear()
        self.ref_to_notification_id.clear()

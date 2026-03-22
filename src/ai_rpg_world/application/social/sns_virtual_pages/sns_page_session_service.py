"""SNS 仮想画面の page session（非永続・player_id ごと）。"""

from __future__ import annotations

from typing import Dict, Optional

from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
    SnsHomeTab,
    SnsSearchMode,
    SnsVirtualPageKind,
)
from ai_rpg_world.application.social.sns_virtual_pages.page_session_state import (
    SnsPageSessionState,
    clamp_page_limit,
)


class SnsPageSessionService:
    """現在画面・ref マップ・スナップショット世代を保持する。ドメインには ref を持ち込まない。"""

    def __init__(self) -> None:
        self._state_by_player: Dict[int, SnsPageSessionState] = {}

    def get_state(self, player_id: int) -> SnsPageSessionState:
        """状態が無い場合は home 既定で作成する（読み取り専用用途向け）。"""
        if player_id not in self._state_by_player:
            self._state_by_player[player_id] = SnsPageSessionState.default_home()
        return self._state_by_player[player_id]

    def on_enter_sns(self, player_id: int) -> None:
        """sns_enter 成功時: home / following に戻し ref・世代を初期化。"""
        self._state_by_player[player_id] = SnsPageSessionState.default_home()

    def on_exit_sns(self, player_id: int) -> None:
        """sns_logout 時: ページ状態を破棄。"""
        self._state_by_player.pop(player_id, None)

    def set_page_kind(self, player_id: int, kind: SnsVirtualPageKind) -> None:
        st = self.get_state(player_id)
        st.page_kind = kind

    def set_home_tab(self, player_id: int, tab: SnsHomeTab) -> None:
        st = self.get_state(player_id)
        st.home_tab = tab

    def set_paging(self, player_id: int, *, limit: Optional[int] = None, offset: Optional[int] = None) -> None:
        st = self.get_state(player_id)
        if limit is not None:
            st.limit = clamp_page_limit(limit)
        if offset is not None:
            st.offset = max(0, int(offset))

    def set_search_context(
        self,
        player_id: int,
        *,
        mode: Optional[SnsSearchMode],
        query: str = "",
    ) -> None:
        st = self.get_state(player_id)
        st.search_mode = mode
        st.search_query = query

    def set_profile_target_user_id(self, player_id: int, user_id: Optional[int]) -> None:
        st = self.get_state(player_id)
        st.profile_target_user_id = user_id

    def set_post_detail_root_post_id(self, player_id: int, post_id: Optional[int]) -> None:
        st = self.get_state(player_id)
        st.post_detail_root_post_id = post_id

    def bump_snapshot_generation(self, player_id: int) -> int:
        """同一条件の再取得などで ref を無効化する。世代を上げて ref マップを空にする。"""
        st = self.get_state(player_id)
        st.snapshot_generation += 1
        st.clear_ref_maps()
        return st.snapshot_generation

    def _next_ref(self, st: SnsPageSessionState, prefix: str) -> str:
        st.ref_seq += 1
        return f"{prefix}_{st.ref_seq:02d}"

    def issue_post_ref(self, player_id: int, post_id: int) -> str:
        st = self.get_state(player_id)
        ref = self._next_ref(st, "r_post")
        st.ref_to_post_id[ref] = post_id
        return ref

    def issue_user_ref(self, player_id: int, user_id: int) -> str:
        st = self.get_state(player_id)
        ref = self._next_ref(st, "r_user")
        st.ref_to_user_id[ref] = user_id
        return ref

    def issue_reply_ref(self, player_id: int, reply_id: int) -> str:
        st = self.get_state(player_id)
        ref = self._next_ref(st, "r_reply")
        st.ref_to_reply_id[ref] = reply_id
        return ref

    def issue_notification_ref(self, player_id: int, notification_id: int) -> str:
        st = self.get_state(player_id)
        ref = self._next_ref(st, "r_notif")
        st.ref_to_notification_id[ref] = notification_id
        return ref

    def resolve_post_ref(self, player_id: int, ref: str) -> Optional[int]:
        return self.get_state(player_id).ref_to_post_id.get(ref)

    def resolve_user_ref(self, player_id: int, ref: str) -> Optional[int]:
        return self.get_state(player_id).ref_to_user_id.get(ref)

    def resolve_reply_ref(self, player_id: int, ref: str) -> Optional[int]:
        return self.get_state(player_id).ref_to_reply_id.get(ref)

    def resolve_notification_ref(self, player_id: int, ref: str) -> Optional[int]:
        return self.get_state(player_id).ref_to_notification_id.get(ref)


__all__ = ["SnsPageSessionService"]

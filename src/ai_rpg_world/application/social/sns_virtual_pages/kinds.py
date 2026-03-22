"""仮想 SNS 画面の種別・タブ・検索モード（LLM 向け契約と一致する文字列値）。"""

from enum import Enum


class SnsVirtualPageKind(str, Enum):
    """画面種別。スナップショット JSON・ツール引数ではこの値を用いる。"""

    HOME = "home"
    POST_DETAIL = "post_detail"
    SEARCH = "search"
    PROFILE = "profile"
    NOTIFICATIONS = "notifications"


class SnsHomeTab(str, Enum):
    """home 画面のタブ。"""

    FOLLOWING = "following"
    POPULAR = "popular"


class SnsSearchMode(str, Enum):
    """search 画面の検索モード。"""

    KEYWORD = "keyword"
    HASHTAG = "hashtag"


__all__ = ["SnsVirtualPageKind", "SnsHomeTab", "SnsSearchMode"]

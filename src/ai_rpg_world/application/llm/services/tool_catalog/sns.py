"""SNS 系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    SnsEnterToolAvailabilityResolver,
    SnsPageKindAvailabilityResolver,
    SnsProfileUpdateAvailabilityResolver,
    SnsToolAvailabilityResolver,
    SnsVirtualPageHomeTabAvailabilityResolver,
    SnsVirtualPageNavigationAvailabilityResolver,
    SnsVirtualPagePagingAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_BLOCK,
    TOOL_NAME_SNS_DELETE_POST,
    TOOL_NAME_SNS_DELETE_REPLY,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_HOME_TIMELINE,
    TOOL_NAME_SNS_LIST_MY_POSTS,
    TOOL_NAME_SNS_LIST_USER_POSTS,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_MARK_ALL_NOTIFICATIONS_READ,
    TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    TOOL_NAME_SNS_OPEN_PAGE,
    TOOL_NAME_SNS_OPEN_REF,
    TOOL_NAME_SNS_PAGE_NEXT,
    TOOL_NAME_SNS_PAGE_REFRESH,
    TOOL_NAME_SNS_SWITCH_TAB,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_LIKE_REPLY,
    TOOL_NAME_SNS_SUBSCRIBE,
    TOOL_NAME_SNS_UNBLOCK,
    TOOL_NAME_SNS_UNFOLLOW,
    TOOL_NAME_SNS_UNSUBSCRIBE,
    TOOL_NAME_SNS_UPDATE_PROFILE,
)

SNS_ENTER_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_ENTER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_ENTER,
    description=(
        "ゲーム内の SNS アプリを開きます（実認証ではありません）。"
        "開くと投稿・取引など SNS モード用ツールが利用可能になります。"
    ),
    parameters=SNS_ENTER_PARAMETERS,
)

SNS_LOGOUT_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_LOGOUT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LOGOUT,
    description=(
        "ゲーム内の SNS アプリを閉じます（実認証のログアウトではありません）。"
        "閉じると SNS モード用ツールは一覧から外れます。"
    ),
    parameters=SNS_LOGOUT_PARAMETERS,
)

SNS_CREATE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "投稿する内容（280文字以内）。"},
        "visibility": {
            "type": "string",
            "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。",
        },
    },
    "required": ["content"],
}
SNS_CREATE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_POST,
    description="SNSに新しい投稿を作成します。",
    parameters=SNS_CREATE_POST_PARAMETERS,
)

SNS_CREATE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "リプライする内容。"},
        "parent_post_id": {"type": "integer", "description": "親ポストのID。parent_reply_id とどちらか必須。"},
        "parent_reply_id": {"type": "integer", "description": "親リプライのID。parent_post_id とどちらか必須。"},
        "visibility": {
            "type": "string",
            "description": "公開範囲。public, followers_only, private のいずれか。省略時または不明な値の場合は public（公開）として扱います。",
        },
    },
    "required": ["content"],
}
SNS_CREATE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_CREATE_REPLY,
    description="ポストまたはリプライに返信します。parent_post_id または parent_reply_id のどちらかを指定してください。",
    parameters=SNS_CREATE_REPLY_PARAMETERS,
)

SNS_LIKE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "post_id": {"type": "integer", "description": "いいねするポストのID。"},
    },
    "required": ["post_id"],
}
SNS_LIKE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_POST,
    description="ポストにいいねします。",
    parameters=SNS_LIKE_POST_PARAMETERS,
)

SNS_LIKE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "reply_id": {"type": "integer", "description": "いいねするリプライのID。"},
    },
    "required": ["reply_id"],
}
SNS_LIKE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIKE_REPLY,
    description="リプライにいいねします。",
    parameters=SNS_LIKE_REPLY_PARAMETERS,
)

SNS_FOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォローするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_FOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_FOLLOW,
    description="指定したユーザーをフォローします。",
    parameters=SNS_FOLLOW_PARAMETERS,
)

SNS_UNFOLLOW_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "フォロー解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNFOLLOW_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNFOLLOW,
    description="指定したユーザーのフォローを解除します。",
    parameters=SNS_UNFOLLOW_PARAMETERS,
)

SNS_SUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_SUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_SUBSCRIBE,
    description="指定したユーザーをサブスクライブします。",
    parameters=SNS_SUBSCRIBE_PARAMETERS,
)

SNS_UNSUBSCRIBE_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "サブスクライブ解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNSUBSCRIBE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNSUBSCRIBE,
    description="指定したユーザーのサブスクライブを解除します。",
    parameters=SNS_UNSUBSCRIBE_PARAMETERS,
)

SNS_BLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロックするユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_BLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_BLOCK,
    description="指定したユーザーをブロックします。",
    parameters=SNS_BLOCK_PARAMETERS,
)

SNS_UNBLOCK_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "ブロック解除するユーザーのID。"},
    },
    "required": ["target_user_id"],
}
SNS_UNBLOCK_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UNBLOCK,
    description="指定したユーザーのブロックを解除します。",
    parameters=SNS_UNBLOCK_PARAMETERS,
)

SNS_DELETE_POST_PARAMETERS = {
    "type": "object",
    "properties": {
        "post_id": {"type": "integer", "description": "削除するポストのID。"},
    },
    "required": ["post_id"],
}
SNS_DELETE_POST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_DELETE_POST,
    description="自分が投稿したポストを削除します。",
    parameters=SNS_DELETE_POST_PARAMETERS,
)

SNS_DELETE_REPLY_PARAMETERS = {
    "type": "object",
    "properties": {
        "reply_id": {"type": "integer", "description": "削除するリプライのID。"},
    },
    "required": ["reply_id"],
}
SNS_DELETE_REPLY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_DELETE_REPLY,
    description="自分が投稿したリプライを削除します。",
    parameters=SNS_DELETE_REPLY_PARAMETERS,
)

SNS_UPDATE_PROFILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "new_display_name": {
            "type": "string",
            "description": "新しい表示名。省略可（他方と併用）。",
        },
        "new_bio": {
            "type": "string",
            "description": "新しい自己紹介。省略可（他方と併用）。",
        },
    },
    "required": [],
}
SNS_UPDATE_PROFILE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_UPDATE_PROFILE,
    description="SNS の表示名または自己紹介を更新します。いずれか一方または両方を指定してください。",
    parameters=SNS_UPDATE_PROFILE_PARAMETERS,
)

SNS_MARK_NOTIFICATION_READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "notification_id": {"type": "integer", "description": "既読にする通知のID。"},
    },
    "required": ["notification_id"],
}
SNS_MARK_NOTIFICATION_READ_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    description="指定した通知を既読にします。",
    parameters=SNS_MARK_NOTIFICATION_READ_PARAMETERS,
)

SNS_MARK_ALL_NOTIFICATIONS_READ_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_MARK_ALL_NOTIFICATIONS_READ_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_MARK_ALL_NOTIFICATIONS_READ,
    description="自分宛ての通知をすべて既読にします。",
    parameters=SNS_MARK_ALL_NOTIFICATIONS_READ_PARAMETERS,
)

SNS_HOME_TIMELINE_PARAMETERS = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "description": "取得件数（省略時は 20、最大 100）。"},
        "offset": {"type": "integer", "description": "先頭からスキップする件数（省略時は 0）。"},
    },
    "required": [],
}
SNS_HOME_TIMELINE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_HOME_TIMELINE,
    description="フォロー中ユーザーのホームタイムライン（投稿一覧）を取得します。",
    parameters=SNS_HOME_TIMELINE_PARAMETERS,
)

SNS_LIST_MY_POSTS_PARAMETERS = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "description": "取得件数（省略時は 20、最大 100）。"},
        "offset": {"type": "integer", "description": "先頭からスキップする件数（省略時は 0）。"},
    },
    "required": [],
}
SNS_LIST_MY_POSTS_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIST_MY_POSTS,
    description="自分の投稿一覧を取得します。",
    parameters=SNS_LIST_MY_POSTS_PARAMETERS,
)

SNS_LIST_USER_POSTS_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_user_id": {"type": "integer", "description": "投稿一覧を見る対象の SNS ユーザー ID。"},
        "limit": {"type": "integer", "description": "取得件数（省略時は 20、最大 100）。"},
        "offset": {"type": "integer", "description": "先頭からスキップする件数（省略時は 0）。"},
    },
    "required": ["target_user_id"],
}
SNS_LIST_USER_POSTS_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_LIST_USER_POSTS,
    description="指定したユーザーの投稿一覧を取得します（閲覧権限に従います）。",
    parameters=SNS_LIST_USER_POSTS_PARAMETERS,
)

_PG_HOME_SEARCH_PROFILE = frozenset({"home", "search", "profile"})
_PG_POST_DETAIL = frozenset({"post_detail"})
_PG_LIKE_POST = frozenset({"home", "post_detail", "search", "profile"})
_PG_DELETE_POST = frozenset({"home", "post_detail", "search", "profile"})
_PG_SOCIAL = frozenset({"profile"})
_PG_NOTIFICATIONS = frozenset({"notifications"})

SNS_VIEW_CURRENT_PAGE_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_VIEW_CURRENT_PAGE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    description="現在の仮想 SNS 画面のスナップショット（JSON）を返します。page-local ref はこの結果に従います。",
    parameters=SNS_VIEW_CURRENT_PAGE_PARAMETERS,
)

SNS_OPEN_PAGE_PARAMETERS = {
    "type": "object",
    "properties": {
        "page": {
            "type": "string",
            "description": "遷移先: home, post_detail, search, profile, notifications のいずれか。",
        },
        "home_tab": {
            "type": "string",
            "description": "page が home のとき: following または popular。",
        },
        "search_mode": {
            "type": "string",
            "description": "page が search のとき: keyword または hashtag。",
        },
        "search_query": {
            "type": "string",
            "description": "page が search のときの検索語（省略可）。",
        },
        "profile_user_ref": {
            "type": "string",
            "description": "page が profile のとき、スナップショットの user ref。省略時は自分のプロフィール。",
        },
        "post_ref": {
            "type": "string",
            "description": "page が post_detail のとき必須。スナップショットの post ref（ルート投稿）。",
        },
    },
    "required": ["page"],
}
SNS_OPEN_PAGE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_OPEN_PAGE,
    description="論理画面へ遷移します。post_detail には post_ref が必要です。",
    parameters=SNS_OPEN_PAGE_PARAMETERS,
)

SNS_OPEN_REF_PARAMETERS = {
    "type": "object",
    "properties": {
        "ref": {
            "type": "string",
            "description": "現在のスナップショットに含まれる page-local ref（r_post_*, r_user_*, r_reply_*, r_notif_*）。",
        },
    },
    "required": ["ref"],
}
SNS_OPEN_REF_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_OPEN_REF,
    description="スナップショット上の ref に対応する画面へ遷移します。",
    parameters=SNS_OPEN_REF_PARAMETERS,
)

SNS_PAGE_NEXT_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_PAGE_NEXT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_PAGE_NEXT,
    description="現在画面の次ページへ進みます（offset を limit 分進める）。",
    parameters=SNS_PAGE_NEXT_PARAMETERS,
)

SNS_PAGE_REFRESH_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
SNS_PAGE_REFRESH_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_PAGE_REFRESH,
    description="同一条件で画面を再取得します（ref の世代が更新されることがあります）。",
    parameters=SNS_PAGE_REFRESH_PARAMETERS,
)

SNS_SWITCH_TAB_PARAMETERS = {
    "type": "object",
    "properties": {
        "tab": {
            "type": "string",
            "description": "home のタブ: following または popular。",
        },
    },
    "required": ["tab"],
}
SNS_SWITCH_TAB_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SNS_SWITCH_TAB,
    description="home 画面で following / popular を切り替えます。",
    parameters=SNS_SWITCH_TAB_PARAMETERS,
)


def get_sns_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """SNS 系ツールの (definition, resolver) 一覧を返す。"""
    enter_resolver = SnsEnterToolAvailabilityResolver()
    sns_resolver = SnsToolAvailabilityResolver()
    pg_create_post = SnsPageKindAvailabilityResolver(_PG_HOME_SEARCH_PROFILE)
    pg_create_reply = SnsPageKindAvailabilityResolver(_PG_POST_DETAIL)
    pg_like_post = SnsPageKindAvailabilityResolver(_PG_LIKE_POST)
    pg_like_reply = SnsPageKindAvailabilityResolver(_PG_POST_DETAIL)
    pg_social = SnsPageKindAvailabilityResolver(_PG_SOCIAL)
    pg_delete_post = SnsPageKindAvailabilityResolver(_PG_DELETE_POST)
    pg_delete_reply = SnsPageKindAvailabilityResolver(_PG_POST_DETAIL)
    pg_profile_update = SnsProfileUpdateAvailabilityResolver()
    pg_notifications = SnsPageKindAvailabilityResolver(_PG_NOTIFICATIONS)
    return [
        (SNS_ENTER_DEFINITION, enter_resolver),
        (SNS_LOGOUT_DEFINITION, sns_resolver),
        (SNS_CREATE_POST_DEFINITION, pg_create_post),
        (SNS_CREATE_REPLY_DEFINITION, pg_create_reply),
        (SNS_LIKE_POST_DEFINITION, pg_like_post),
        (SNS_LIKE_REPLY_DEFINITION, pg_like_reply),
        (SNS_FOLLOW_DEFINITION, pg_social),
        (SNS_UNFOLLOW_DEFINITION, pg_social),
        (SNS_SUBSCRIBE_DEFINITION, pg_social),
        (SNS_UNSUBSCRIBE_DEFINITION, pg_social),
        (SNS_BLOCK_DEFINITION, pg_social),
        (SNS_UNBLOCK_DEFINITION, pg_social),
        (SNS_DELETE_POST_DEFINITION, pg_delete_post),
        (SNS_DELETE_REPLY_DEFINITION, pg_delete_reply),
        (SNS_UPDATE_PROFILE_DEFINITION, pg_profile_update),
        (SNS_MARK_NOTIFICATION_READ_DEFINITION, pg_notifications),
        (SNS_MARK_ALL_NOTIFICATIONS_READ_DEFINITION, pg_notifications),
        (SNS_HOME_TIMELINE_DEFINITION, sns_resolver),
        (SNS_LIST_MY_POSTS_DEFINITION, sns_resolver),
        (SNS_LIST_USER_POSTS_DEFINITION, sns_resolver),
    ]


def get_sns_virtual_page_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """仮想 SNS 画面ナビゲーション用ツール（SnsPageQueryService 配線時のみ登録）。"""
    nav = SnsVirtualPageNavigationAvailabilityResolver()
    paging = SnsVirtualPagePagingAvailabilityResolver()
    home_tab = SnsVirtualPageHomeTabAvailabilityResolver()
    return [
        (SNS_VIEW_CURRENT_PAGE_DEFINITION, nav),
        (SNS_OPEN_PAGE_DEFINITION, nav),
        (SNS_OPEN_REF_DEFINITION, nav),
        (SNS_PAGE_NEXT_DEFINITION, paging),
        (SNS_PAGE_REFRESH_DEFINITION, nav),
        (SNS_SWITCH_TAB_DEFINITION, home_tab),
    ]


__all__ = [
    "get_sns_specs",
]

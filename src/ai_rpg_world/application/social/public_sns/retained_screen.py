"""取得時の公開SNS画面を予算内で保持する。時刻経過による再取得はしない。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.social.public_sns.contracts import (
    PublicSnsContentDto,
    PublicSnsNotificationDto,
    PublicSnsNotificationPage,
    PublicSnsPage,
    PublicSnsThread,
)

MAX_SCREEN_CHARS = 12000
MAX_SCREEN_ROWS = 20
MAX_BODY_CHARS = 400


def _bounded(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…（省略）"


def _content_row(item: PublicSnsContentDto) -> str:
    return "\n".join(
        (
            f"対象: {item.target_id}" + (f" / 返信元: {item.parent_target_id}" if item.parent_target_id else ""),
            f"{_bounded(item.author_display_name, 80)} / 人物: {item.author_target_id} / {item.created_at.isoformat()}",
            _bounded(item.content, MAX_BODY_CHARS),
        )
    )


def render_public_sns_screen(view: str, page: PublicSnsPage | PublicSnsThread | PublicSnsNotificationPage) -> str:
    """上限内の全対象IDと次の取得位置を残し、本文だけを必要に応じて短くする。"""
    headings = {"posts": "公開SNS: 投稿一覧", "thread": "公開SNS: 投稿と返信", "inbox": "公開SNS: 受信箱"}
    rows: list[str] = [headings[view], "表示条件: 公開され、現在閲覧できる内容のみ"]
    items: tuple[PublicSnsContentDto | PublicSnsNotificationDto, ...]
    if isinstance(page, PublicSnsThread):
        if len(page.ancestors) > 3:
            rows.append(f"前の文脈{len(page.ancestors) - 3}件は省略しています。")
        rows.extend(_content_row(ancestor) for ancestor in page.ancestors[-3:])
        rows.append(_content_row(page.selected))
        items = page.replies.items
        cursor = page.replies.next_cursor
    else:
        items = page.items
        cursor = page.next_cursor
    if len(items) > MAX_SCREEN_ROWS:
        raise ValueError("画面の取得件数が上限を超えています")
    for item in items:
        if isinstance(item, PublicSnsContentDto):
            rows.append(_content_row(item))
        else:
            row = f"{_bounded(item.actor_display_name, 80)} / 人物: {item.actor_target_id} / {item.created_at.isoformat()} / {_bounded(item.kind, 80)}"
            if item.target_id:
                row += f"\n対象: {item.target_id}"
            if item.content:
                row += "\n" + _bounded(item.content, MAX_BODY_CHARS)
            rows.append(row)
    if not items:
        rows.append("表示する項目はありません。")
    rows.append(f"続き: {cursor}" if cursor else "続き: なし（この取得範囲の終端）")
    text = "\n\n".join(rows)
    # 取り除いた行を飛ばす不正なcursorを返さない。型の境界が破られた時は
    # 画面を入れ替える前に止め、呼出し側に明示的な失敗を返す。
    if len(text) > MAX_SCREEN_CHARS:
        raise ValueError("画面の文字数が上限を超えています")
    return text


@dataclass(frozen=True)
class PublicSnsScreen:
    view: str
    text: str
    provenance: ExecutionProvenance | None
    target_ids: tuple[str, ...] = ()
    notification_ids: tuple[str, ...] = ()
    generation: int = 1


class PublicSnsScreenStore:
    """一人につき一画面だけを保持し、closeで消す世界内の状態。"""

    def __init__(self) -> None:
        self._screens: dict[int, PublicSnsScreen] = {}
        self._requests: dict[int, dict[str, Any]] = {}
        self._presented: dict[int, int] = {}

    def get(self, player_id: int) -> PublicSnsScreen | None:
        return self._screens.get(player_id)

    def show(
        self,
        player_id: int,
        view: str,
        page: PublicSnsPage | PublicSnsThread | PublicSnsNotificationPage,
        provenance: ExecutionProvenance | None,
        *,
        request_cursor: str | None = None,
    ) -> PublicSnsScreen:
        items = (
            (*page.ancestors[-3:], page.selected, *page.replies.items)
            if isinstance(page, PublicSnsThread)
            else page.items
        )
        targets = tuple(item.target_id for item in items if item.target_id)
        notices = tuple(item.notification_id for item in items if hasattr(item, "notification_id"))
        text = render_public_sns_screen(view, page)
        text += f"\n取得位置: {request_cursor or '先頭'}"
        text += f"\n\n取得時点: {datetime.now(timezone.utc).isoformat()} / 表示範囲: {len(items)}件"
        if len(text) > MAX_SCREEN_CHARS:
            raise ValueError("画面の文字数が上限を超えています")
        previous = self._screens.get(player_id)
        generation = previous.generation + 1 if previous else 1
        screen = PublicSnsScreen(view, text, provenance, targets, notices, generation)
        self._screens[player_id] = screen
        return screen

    def close(self, player_id: int) -> None:
        self._screens.pop(player_id, None)
        self._presented.pop(player_id, None)

    def record_request(
        self, player_id: int, view: str | None, status: str, provenance: ExecutionProvenance | None
    ) -> dict[str, Any]:
        record = {"view": view, "status": status, "provenance": provenance.to_dict() if provenance else None}
        self._requests[player_id] = record
        return dict(record)

    def last_request(self, player_id: int) -> dict[str, Any] | None:
        return self._requests.get(player_id)

    def confirm_presented(self, player_id: int, generation: int | None) -> None:
        screen = self.get(player_id)
        if screen is not None and screen.generation == generation:
            self._presented[player_id] = screen.generation

    def presentation_status(self, player_id: int) -> str:
        request = self._requests.get(player_id, {})
        if request.get("status") == "failed_retained":
            return "前回の閲覧要求は失敗しました。以前に取得した画面を保持しています。"
        if request.get("status") == "failed_empty":
            return "前回の閲覧要求は失敗しました。表示中の画面はありません。"
        screen = self.get(player_id)
        if screen is None:
            return "現在の画面: 閉じています。"
        if self._presented.get(player_id) == screen.generation:
            return "現在の画面: 以前に取得した内容を保持しています。"
        return "現在の画面: 新しく取得した内容です。"

    def capture(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "screens": [
                {
                    "player_id": pid,
                    "view": screen.view,
                    "text": screen.text,
                    "provenance": screen.provenance.to_dict() if screen.provenance else None,
                    "target_ids": list(screen.target_ids),
                    "notification_ids": list(screen.notification_ids),
                    "generation": screen.generation,
                }
                for pid, screen in sorted(self._screens.items())
            ],
            "requests": {str(pid): dict(request) for pid, request in self._requests.items()},
            "presented": {str(pid): generation for pid, generation in self._presented.items()},
        }

    def restore(self, data: dict[str, Any]) -> None:
        if data.get("schema_version") != 1 or not isinstance(data.get("screens"), list):
            raise ValueError("公開SNS画面の保存形式が不正です")
        screens: dict[int, PublicSnsScreen] = {}
        for row in data["screens"]:
            pid, view, text = row["player_id"], row["view"], row["text"]
            if isinstance(pid, bool) or not isinstance(pid, int) or pid < 0 or pid in screens:
                raise ValueError("公開SNS画面の人物識別子が不正です")
            if view not in {"inbox", "posts", "thread"} or not isinstance(text, str) or len(text) > MAX_SCREEN_CHARS:
                raise ValueError("公開SNS画面の内容が不正です")
            source = row.get("provenance")
            targets = row.get("target_ids", [])
            notices = row.get("notification_ids", [])
            if any(
                not isinstance(values, list)
                or len(values) > 24
                or any(not isinstance(v, str) or len(v) > 256 for v in values)
                for values in (targets, notices)
            ):
                raise ValueError("公開SNS画面の対象識別子が不正です")
            generation = row.get("generation", 1)
            if type(generation) is not int or generation < 1:
                raise ValueError("公開SNS画面の世代が不正です")
            provenance = ExecutionProvenance.from_dict(source) if source else None
            if provenance is not None and provenance.actor_player_id != pid:
                raise ValueError("公開SNS画面の出典が人物と一致しません")
            screens[pid] = PublicSnsScreen(view, text, provenance, tuple(targets), tuple(notices), generation)
        requests = data.get("requests", {})
        presented = data.get("presented", {})
        if not isinstance(requests, dict) or not isinstance(presented, dict):
            raise ValueError("公開SNSの表示要求が不正です")
        decoded_requests = {}
        for raw_pid, request in requests.items():
            pid = int(raw_pid)
            if (
                pid < 0
                or not isinstance(request, dict)
                or request.get("status") not in {"refreshed", "closed", "failed_retained", "failed_empty"}
                or request.get("view") not in {"inbox", "posts", "thread", "close", None}
            ):
                raise ValueError("公開SNSの表示要求が不正です")
            source = request.get("provenance")
            if source is not None and ExecutionProvenance.from_dict(source).actor_player_id != pid:
                raise ValueError("公開SNSの表示要求の出典が不正です")
            decoded_requests[pid] = dict(request)
        decoded_presented = {}
        for raw_pid, generation in presented.items():
            pid = int(raw_pid)
            if pid < 0 or type(generation) is not int or generation < 1:
                raise ValueError("公開SNSの表示世代が不正です")
            decoded_presented[pid] = generation
        self._screens = screens
        self._requests = decoded_requests
        self._presented = decoded_presented

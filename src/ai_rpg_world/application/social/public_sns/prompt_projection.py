"""保存済み観測を変えずに、公開SNSの通知本文を一つの表示予算へ収める。"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
    format_observation_line_for_recent_events,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsNotificationDto
from ai_rpg_world.application.social.public_sns.retained_screen import PublicSnsScreenStore

_KINDS = {'reply': '返信', 'mention': 'メンション', 'follow': 'フォロー', 'like': 'いいね'}


def notification_observation(notification: PublicSnsNotificationDto, provenance: ExecutionProvenance | None) -> ObservationOutput:
    kind = _KINDS.get(notification.kind.lower(), '通知')
    header = f'公開SNS: {notification.actor_display_name[:30]}から{kind}。人物: {notification.actor_target_id}'
    if notification.target_id:
        header += f' / 対象: {notification.target_id}'
    prose = header + (f'\n{notification.content}' if notification.content else '')
    return ObservationOutput(prose, {
        'type': 'public_sns_notification', 'notification_id': notification.notification_id,
        'actor_name': notification.actor_display_name, 'actor_target_id': notification.actor_target_id,
        'target_id': notification.target_id, 'content': notification.content, 'kind': notification.kind,
        'receipt': header,
        'execution_provenance': provenance.to_dict() if provenance else None,
    }, observation_category='social', schedules_turn=False, breaks_movement=False)


class PublicSnsPromptProjection:
    """文字数はUnicode文字単位。表示の確定は実際の応答を受けた時だけ行う。"""

    def __init__(self, screens: PublicSnsScreenStore, *, budget_chars: int = 6000, header_chars_provider: Callable[[int], int] | None = None) -> None:
        if type(budget_chars) is not int or not 512 <= budget_chars <= 24000:
            raise ValueError('SNS通知予算は512以上24000以下の文字数が必要です')
        self._screens = screens
        self._budget = budget_chars
        self._header_chars = header_chars_provider or (lambda player_id: 0)
        # 本文は観測と永続受信箱にある。ここには未表示の識別子だけを持つ。
        self._pending: dict[int, set[str]] = {}
        self._received: dict[int, set[str]] = {}

    def pending_count(self, player_id: int) -> int:
        return len(self._pending.get(player_id, set()))

    def has_received(self, player_id: int, notification_id: str) -> bool:
        return notification_id in self._received.get(player_id, set())

    def note_incoming(self, player_id: int, notification_id: str) -> None:
        self._received.setdefault(player_id, set()).add(notification_id)
        self._pending.setdefault(player_id, set()).add(notification_id)

    def confirm_shown(self, player_id: int, notification_ids: Sequence[str]) -> None:
        self._pending.setdefault(player_id, set()).difference_update(notification_ids)

    def project(self, player_id: Any, entries: list[UnifiedRecentEventEntry]) -> tuple[list[UnifiedRecentEventEntry], tuple[str, ...]]:
        pid = int(getattr(player_id, 'value', player_id))
        pending = self._pending.get(pid, set())
        screen = self._screens.get(pid)
        visible_targets = set(screen.target_ids) if screen else set()
        shown: set[str] = set(screen.notification_ids) & pending if screen else set()
        replacements: dict[int, UnifiedRecentEventEntry] = {}
        remaining = max(0, self._budget - self._header_chars(pid) - 90)  # 件数行と箇条書きの余白。
        first: int | None = None
        seen: set[str] = set()
        def priority(index: int) -> tuple[int, int]:
            payload = entries[index].payload
            facts = payload.output.structured if isinstance(payload, ObservationEntry) else {}
            return (0 if str(facts.get("kind", "")).lower() in {"reply", "mention"} else 1, -index)

        for index in sorted(range(len(entries)), key=priority):
            entry = entries[index]
            observation = entry.payload
            if not isinstance(observation, ObservationEntry) or observation.output.structured.get('type') != 'public_sns_notification':
                continue
            first = index
            facts = observation.output.structured
            notification_id = str(facts.get('notification_id') or '')
            target = facts.get('target_id')
            receipt = str(facts.get('receipt') or '公開SNSの通知が届きました。')
            # 不正に長い識別子は切り詰めて別の識別子に見せず、受信箱へ残す。
            if len(receipt) > 512 or notification_id in seen:
                prose = ''
            else:
                seen.add(notification_id)
                body_needed = notification_id in pending and target not in visible_targets
                prose = observation.output.prose if body_needed else receipt
                projected = replace(observation, output=replace(observation.output, prose=prose))
                cost = len(format_observation_line_for_recent_events(projected)) + 3
                fully_shown = True
                if cost > remaining and body_needed:
                    # actor/targetは短縮しない。本文だけ残量まで表示し、残りは
                    # 受信箱から読めると明示する。部分表示は表示済みにしない。
                    marker = '…（本文の続きは受信箱）'
                    receipt_entry = replace(observation, output=replace(observation.output, prose=receipt + '\n' + marker))
                    receipt_cost = len(format_observation_line_for_recent_events(receipt_entry)) + 3
                    available_body = max(0, remaining - receipt_cost)
                    if receipt_cost <= remaining:
                        prose = receipt + '\n' + str(facts.get('content') or '')[:available_body] + marker
                        cost = receipt_cost + available_body
                        fully_shown = False
                if cost > remaining:
                    prose = ''
                else:
                    remaining -= cost
                    if notification_id in pending and fully_shown:
                        shown.add(notification_id)
            replacements[index] = replace(entry, payload=replace(observation, output=replace(observation.output, prose=prose)))
        overflow = len(pending - shown)
        projected_entries = [replacements.get(i, entry) for i, entry in enumerate(entries)]
        if overflow and first is not None:
            entry = projected_entries[first]
            obs = entry.payload
            if not isinstance(obs, ObservationEntry):
                raise TypeError("SNS通知の表示対象が観測ではありません")
            footer = f'公開SNS: 未表示の通知が{overflow}件あります。受信箱で確認できます。'
            text = (obs.output.prose + '\n' if obs.output.prose else '') + footer
            projected_entries[first] = replace(entry, payload=replace(obs, output=replace(obs.output, prose=text)))
        return projected_entries, tuple(sorted(shown))

    def capture(self) -> dict[str, Any]:
        return {'schema_version': 1, 'pending': {str(pid): sorted(ids) for pid, ids in sorted(self._pending.items())}, 'received': {str(pid): sorted(ids) for pid, ids in sorted(self._received.items())}}

    def restore(self, data: dict[str, Any]) -> None:
        if data.get('schema_version') != 1 or not isinstance(data.get('pending'), dict):
            raise ValueError('SNS通知の表示状態が不正です')
        pending: dict[int, set[str]] = {}
        for key, ids in data['pending'].items():
            pid = int(key)
            if pid < 0 or not isinstance(ids, list) or any(not isinstance(i, str) or not i or len(i) > 256 for i in ids):
                raise ValueError('SNS通知の表示状態が不正です')
            pending[pid] = set(ids)
        received = data.get("received")
        if not isinstance(received, dict):
            raise ValueError("SNS通知の配信状態が不正です")
        decoded = {}
        for key, ids in received.items():
            pid = int(key)
            if pid < 0 or not isinstance(ids, list) or any(not isinstance(i, str) or not i or len(i) > 256 for i in ids):
                raise ValueError("SNS通知の配信状態が不正です")
            decoded[pid] = set(ids)
        if any(not ids <= decoded.get(pid, set()) for pid, ids in pending.items()):
            raise ValueError("未表示の通知に配信記録がありません")
        self._pending = pending
        self._received = decoded

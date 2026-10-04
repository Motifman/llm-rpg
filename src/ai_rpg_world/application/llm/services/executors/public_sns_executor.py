"""公開SNSの二つの操作を通常の一手として実行する。"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.execution_provenance import current_execution_provenance
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsInvalidRequestError, PublicSnsUnavailableError
from ai_rpg_world.application.social.public_sns.retained_screen import PublicSnsScreenStore


class PublicSnsToolExecutor:
    def __init__(self, read_service: Any, command_service: Any, screens: PublicSnsScreenStore) -> None:
        self._reads = read_service
        self._commands = command_service
        self._screens = screens

    @staticmethod
    def _invalid() -> LlmCommandResultDto:
        return LlmCommandResultDto(False, '指定したSNS操作の引数を確認してください。', error_code='SNS_INVALID_REQUEST')

    def read(self, player_id: int, args: dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        view = args.get('view')
        view = view if isinstance(view, str) and view in {'inbox', 'posts', 'thread', 'close'} else None
        try:
            result = self._read(player_id, args, runtime_context)
        except Exception:
            status = 'failed_retained' if self._screens.get(player_id) else 'failed_empty'
            self._screens.record_request(player_id, view, status, current_execution_provenance())
            raise
        screen = self._screens.get(player_id)
        status = ('closed' if view == 'close' else 'refreshed') if result.success else ('failed_retained' if screen else 'failed_empty')
        request = self._screens.record_request(player_id, view, status, current_execution_provenance())
        return replace(result, trace_payload={**(result.trace_payload or {}), 'sns_request': request,
            'retained_screen_provenance': screen.provenance.to_dict() if screen and screen.provenance else None})

    def _read(self, player_id: int, args: dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        view = args.get('view')
        if not isinstance(view, str) or view not in {'inbox', 'posts', 'thread', 'close'}:
            return self._invalid()
        if view == 'close':
            if any(args.get(key) is not None for key in ('target_id', 'cursor', 'limit')):
                return self._invalid()
            self._screens.close(player_id)
            return LlmCommandResultDto(True, '公開SNSの画面を閉じました。')
        limit = args.get('limit', 10)
        cursor = args.get('cursor')
        target = args.get('target_id')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            return self._invalid()
        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            return self._invalid()
        if (view == 'thread' and (not isinstance(target, str) or not target)) or (view != 'thread' and target is not None):
            return self._invalid()
        try:
            if view == 'posts':
                page = self._reads.read_posts(player_id, cursor=cursor, limit=limit)
            elif view == 'inbox':
                page = self._reads.read_notifications(player_id, cursor=cursor, limit=limit)
            else:
                page = self._reads.read_target(player_id, target, cursor=cursor, limit=limit)
            screen = self._screens.show(player_id, view, page, current_execution_provenance(), request_cursor=cursor)
        except PublicSnsUnavailableError:
            return LlmCommandResultDto(False, 'この投稿は現在表示できません', error_code='SNS_UNAVAILABLE')
        except (PublicSnsInvalidRequestError, ValueError):
            return self._invalid()
        labels = {'inbox': '受信箱', 'posts': '投稿一覧', 'thread': '投稿と返信'}
        return LlmCommandResultDto(True, f'公開SNSの{labels[view]}を読みました。', trace_payload={
            'sns_view': view, 'screen_chars': len(screen.text),
            'screen_provenance': screen.provenance.to_dict() if screen.provenance else None,
        })

    def publish(self, player_id: int, args: dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        action, content, target = args.get('action'), args.get('content'), args.get('target_id')
        if not isinstance(action, str) or action not in {'new', 'reply'} or not isinstance(content, str) or not content.strip() or len(content) > 280:
            return self._invalid()
        if (action == 'reply' and (not isinstance(target, str) or not target)) or (action == 'new' and target is not None):
            return self._invalid()
        try:
            published = self._commands.publish(player_id, content, target_id=target)
        except PublicSnsUnavailableError:
            return LlmCommandResultDto(False, 'この投稿は現在表示できません', error_code='SNS_UNAVAILABLE')
        except PublicSnsInvalidRequestError:
            return self._invalid()
        except CommandPostCommitException as exc:
            published = getattr(exc, 'result', None)
            published_id = getattr(published, 'target_id', None)
            return LlmCommandResultDto(True, '投稿は確定しました。通知の配送は未完了です。同じ投稿を繰り返さないでください。', trace_payload={'target_id': published_id, 'notification_delivery_pending': True})
        verb = '投稿' if action == 'new' else '返信'
        return LlmCommandResultDto(True, f'公開SNSへ{verb}しました。対象: {published.target_id}', trace_payload={'target_id': published.target_id})

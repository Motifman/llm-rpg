"""``IntentResolutionService``: intent を queue 経由で resolve するアプリ層サービス。

責務
----
1. LLM ツール呼び出しを ``Intent`` VO に変換し ``IntentQueue`` に submit する
2. queue から drain した intent をフェーズ順に既存の handler 関数で解決する
3. 解決結果を ``LlmCommandResultDto`` として返す

設計判断
--------
- 既存の handler シグネチャ ``(player_id: int, args: Mapping) -> LlmCommandResultDto``
  はそのまま再利用する。tool executor の書き換えは不要。
- ``submit_and_resolve_immediately``: orchestrator が即時応答を返す現状フローに
  そのまま乗せられる。intent は queue に乗ってから即 drain → resolve される。
- ``resolve_drained``: 既に drain 済みの intent リストを一括で resolve する。
  将来「複数 LLM 呼び出しを batching し post-tick で一斉解決」する経路に
  使う。本 PR では未配線。

なぜ queue を一度経由するか (即時 resolve でも)
-----------------------------------------------
- intent_id が払い出されるので、後続の ``ActionFailed{intent}`` 観測 (PR5) で
  「どの intent が失敗したか」が再現できる
- 同 tick 内の他 intent との順序関係が決定論的になる (今は 1 件だけだが、
  PR で `resolve_drained` 経路に切り替えるとそのまま意味を持つ)
- PR6 (アクション持続時間) で `complete_at_tick` が未来になる場合に対応する
  ロジックを集約できる
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional, Sequence

from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

# (player_id_int, args_dict) -> LlmCommandResultDto
ToolHandler = Callable[[int, Mapping[str, Any]], LlmCommandResultDto]

# (intent, dto) -> None — 解決後に呼ばれるオブザーバ (PR5: ActionFailed 観測)
ResolutionObserver = Callable[[Intent, LlmCommandResultDto], None]


class IntentResolutionService:
    """Intent 経由でツール実行を行うアプリケーションサービス。"""

    def __init__(
        self,
        handler_map: Mapping[str, ToolHandler],
        intent_queue: IntentQueue,
        intent_id_generator: IntentIdGenerator,
        tick_provider: Callable[[], WorldTick],
        failure_observer: Optional[ResolutionObserver] = None,
    ) -> None:
        if not isinstance(handler_map, Mapping):
            raise TypeError("handler_map must be Mapping")
        if not isinstance(intent_queue, IntentQueue):
            raise TypeError("intent_queue must be IntentQueue")
        if not isinstance(intent_id_generator, IntentIdGenerator):
            raise TypeError(
                "intent_id_generator must be IntentIdGenerator"
            )
        if not callable(tick_provider):
            raise TypeError("tick_provider must be callable")
        if failure_observer is not None and not callable(failure_observer):
            raise TypeError("failure_observer must be callable or None")
        self._handler_map: dict[str, ToolHandler] = dict(handler_map)
        self._intent_queue = intent_queue
        self._intent_id_generator = intent_id_generator
        self._tick_provider = tick_provider
        self._failure_observer = failure_observer

    def submit_and_resolve_immediately(
        self,
        player_id: int,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> LlmCommandResultDto:
        """Intent を queue に積み、自分の intent だけを取り出して resolve する。

        ``drain_ready_for_tick`` は使わない。複数の caller が close interleave
        した場合に他 caller の intent を巻き込んでしまう race を避けるため、
        即時 path は「自分が submit した intent を ID で extract → resolve」と
        する。

        失敗時 (handler が見つからない / queue が拒否する) は失敗 DTO を返し、
        intent は queue に残らない。
        """
        current_tick = self._tick_provider()
        intent = self._build_intent(
            player_id_int=player_id,
            tool_name=tool_name,
            arguments=arguments,
            current_tick=current_tick,
        )
        try:
            self._intent_queue.submit(intent)
        except Exception as exc:
            logger.warning(
                "Intent submission rejected: tool=%s player=%s err=%s",
                tool_name,
                player_id,
                exc,
            )
            return LlmCommandResultDto(
                success=False,
                message=f"intent の登録に失敗しました: {exc}",
                error_code="INTENT_SUBMISSION_REJECTED",
            )
        try:
            extracted = self._intent_queue.remove(intent.intent_id)
        except Exception:
            # submit 直後に他者が remove することは現状の単一スレッド前提では
            # 起きないが、防御的にハンドリングする。
            logger.exception(
                "submitted intent %s vanished from queue before extract",
                intent.intent_id.value,
            )
            return LlmCommandResultDto(
                success=False,
                message="intent の解決に失敗しました (内部エラー)。",
                error_code="INTENT_RESOLVE_INTERNAL",
            )
        dto = self._resolve_one(extracted)
        self._notify_failure(extracted, dto)
        return dto

    def _resolve_drained(
        self, intents: Sequence[Intent]
    ) -> list[tuple[Intent, LlmCommandResultDto]]:
        """drain 済み intent をフェーズ順そのままに resolve する (private)。

        将来 PR で post-tick batching の経路を追加する際の seam。本 PR では
        production caller を持たず、テスト用途のみ。シグネチャは PR6+ で
        確定する。
        """
        results: list[tuple[Intent, LlmCommandResultDto]] = []
        for intent in intents:
            dto = self._resolve_one(intent)
            self._notify_failure(intent, dto)
            results.append((intent, dto))
        return results

    def _notify_failure(
        self, intent: Intent, dto: LlmCommandResultDto
    ) -> None:
        """失敗 DTO の場合に failure_observer を呼ぶ。

        observer の例外は resolve 結果を倒さないように吸収する (best-effort)。
        """
        if dto.success or self._failure_observer is None:
            return
        try:
            self._failure_observer(intent, dto)
        except Exception:
            logger.exception(
                "failure_observer raised for intent=%s tool=%s",
                intent.intent_id.value,
                intent.tool_name,
            )

    def _resolve_one(self, intent: Intent) -> LlmCommandResultDto:
        handler = self._handler_map.get(intent.tool_name)
        if handler is None:
            return LlmCommandResultDto(
                success=False,
                message="未知のツールです。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            return handler(intent.player_id.value, dict(intent.arguments))
        except Exception as exc:
            logger.exception(
                "Intent handler raised for tool=%s player=%s",
                intent.tool_name,
                intent.player_id.value,
            )
            return LlmCommandResultDto(
                success=False,
                message=f"ツール実行中に例外が発生しました: {exc}",
                error_code="INTENT_HANDLER_RAISED",
            )

    def _build_intent(
        self,
        player_id_int: int,
        tool_name: str,
        arguments: Mapping[str, Any],
        current_tick: WorldTick,
    ) -> Intent:
        return Intent(
            intent_id=self._intent_id_generator.next_id(),
            player_id=PlayerId(player_id_int),
            tool_name=tool_name,
            arguments=dict(arguments),  # 防御的コピー
            phase=phase_for_tool(tool_name),
            submitted_at_tick=current_tick,
            complete_at_tick=current_tick,  # instant action (PR6 で拡張)
        )

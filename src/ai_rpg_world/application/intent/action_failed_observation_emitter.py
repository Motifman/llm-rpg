"""Intent の解決失敗を「該当プレイヤーへの観測」に変換する emitter。

なぜ
----
intent が失敗したとき (`dto.success=False`) に、LLM に「お前の行動はこういう
理由で失敗した」を伝える観測を投入する。これにより:

- LLM は失敗を次の判断材料にできる (例: 「ゴブリンが逃げた」→ 別の方向に動く)
- 同 tick 競合で負けた側に `LOST_RACE` を観測として返せる (PR6+ で生かす)

設計
----
- `IntentResolutionService.submit_and_resolve_immediately` から失敗 DTO が
  返ったときに、本 emitter が呼び出される
- 観測は `self_only` カテゴリ + `schedules_turn=True` で投入。失敗を見た LLM
  が即座にリカバー行動を取れるようにする
- 観測 buffer への append が失敗しても resolve 自体は妨げない (best-effort)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.intent.value_object.intent import Intent

logger = logging.getLogger(__name__)

# 観測化しない error_code 群。以下を除外:
# - LLM API レベルの失敗 (NO_TOOL_CALL / LLM_API_CALL_FAILED 等): intent 解決
#   起源ではない
# - 配線・内部エラー (UNKNOWN_TOOL / INTENT_HANDLER_RAISED 等): LLM 側で
#   リカバー不能。LLM に伝えると「未知のツールが失敗した」を「行動の失敗」と
#   誤認して同じツールを再試行するループの素になる
_NON_ACTION_FAILURE_CODES = frozenset({
    # LLM API レベル
    "NO_TOOL_CALL",
    "LLM_API_CALL_FAILED",
    "LLM_RATE_LIMIT",
    "LLM_AUTHENTICATION_ERROR",
    # 配線・内部エラー
    "UNKNOWN_TOOL",
    "INTENT_HANDLER_RAISED",
    "INTENT_SUBMISSION_REJECTED",
    "INTENT_RESOLVE_INTERNAL",
})


def _is_action_failure(dto: LlmCommandResultDto) -> bool:
    """observation 化すべき「行動失敗」かどうか。"""
    if dto.success:
        return False
    # error_code が無い失敗は安全側に倒して観測投入する
    if dto.error_code is None:
        return True
    return dto.error_code not in _NON_ACTION_FAILURE_CODES


class ActionFailedObservationEmitter:
    """intent 解決失敗を当該プレイヤーへの観測に変換するクラス。"""

    def __init__(
        self,
        observation_appender: ObservationAppender,
        turn_scheduler: ObservationTurnScheduler,
        now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        time_label_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._observation_appender = observation_appender
        self._turn_scheduler = turn_scheduler
        self._now_provider = now_provider
        self._time_label_provider = time_label_provider

    def on_resolution_failure(
        self, intent: Intent, dto: LlmCommandResultDto
    ) -> None:
        """resolve 結果が失敗のとき呼ばれるコールバック。

        `success=True` や LLM API 起源の失敗は除外する。
        """
        if not _is_action_failure(dto):
            return
        output = self._build_observation(intent, dto)
        try:
            time_label = (
                self._time_label_provider()
                if self._time_label_provider is not None
                else None
            )
            self._observation_appender.append(
                intent.player_id,
                output,
                self._now_provider(),
                time_label,
            )
        except Exception:
            logger.exception(
                "Failed to append ActionFailed observation for intent %s",
                intent.intent_id.value,
            )
            return
        try:
            self._turn_scheduler.maybe_schedule(intent.player_id, output)
        except Exception:
            logger.exception(
                "Failed to schedule turn after ActionFailed for player %s",
                intent.player_id.value,
            )

    def _build_observation(
        self, intent: Intent, dto: LlmCommandResultDto
    ) -> ObservationOutput:
        prose = (
            f"{intent.tool_name} を試みたが失敗した: {dto.message}"
            if dto.message
            else f"{intent.tool_name} は失敗した。"
        )
        if dto.remediation:
            prose = f"{prose} 修正のヒント: {dto.remediation}"
        # observation_category="self_only": ActionFailed は「自分の行動が世界に
        # 拒否された」体験で、他エージェントには本質的に観測されない (副作用
        # としての観測は別途 environment カテゴリで投入される想定)。
        #
        # schedules_turn は DTO の should_reschedule に従う: ハンドラが
        # 「次 tick で再試行しても意味がない」と判断した失敗 (例: 同じラベル
        # を再度指定するだけ) はターンを積まずに次の観測 / heartbeat を待つ。
        # これで「失敗 → 即同じ行動 → 失敗 → ...」の無限ループを集約レベルで
        # 抑止する。
        return ObservationOutput(
            prose=prose,
            structured={
                "type": "action_failed",
                "intent_id": intent.intent_id.value,
                "tool_name": intent.tool_name,
                "error_code": dto.error_code,
                "message": dto.message,
                "remediation": dto.remediation,
            },
            observation_category="self_only",
            schedules_turn=dto.should_reschedule,
        )

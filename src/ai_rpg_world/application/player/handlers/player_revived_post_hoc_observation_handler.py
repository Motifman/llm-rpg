"""PlayerRevivedEvent を受けて本人の observation_buffer に post hoc summary を
注入する handler (Issue #621 Phase 5)。

ダウン中の player は LLM ターンが回らず観測も配信されない (Phase 4 で
recipient から除外)。意識が戻った直後に「自分は意識を失っていた」「誰が
助けてくれた」を遡及的に観測として渡し、エージェントが「気を失っていた間に
何があったか」を初手の物語として読めるようにする。

仕様:
- prose: 「{N} tick の間、意識を失っていた。{caregiver_name} に介抱されて意識が戻った。」
- caregiver_player_id=None: caregiver 句は省略 (「{N} tick の間、意識を失っていた。
  意識が戻った。」)
- grace_timer に downed_at_tick が無い (= 想定外経路): 時間表示を省略
  (「数 tick の間、意識を失っていた。…」) で fail-safe append
- schedules_turn=True: 復活直後に自分のターンを駆動する

handler 順序の前提: PipelineEventPublisher は登録順に dispatch するため、
本 handler は ``PlayerRevivedOutcomeHandler`` (= grace_timer.cancel を呼ぶ)
よりも先に register すること。先に cancel されると downed_at_tick が消えて
時間が不明になる。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

CaregiverNameResolver = Callable[[PlayerId], Optional[str]]
"""``PlayerId`` → 表示名 を引く resolver。未解決 (persona 未登録 等) は None。"""


class PlayerRevivedPostHocObservationHandler(EventHandler[PlayerRevivedEvent]):
    """PlayerRevivedEvent → 本人 buffer に post hoc summary を append する。"""

    def __init__(
        self,
        *,
        grace_timer: PlayerDeathGraceTimer,
        observation_appender: ObservationAppender,
        current_tick_provider: Callable[[], int],
        caregiver_name_resolver: CaregiverNameResolver,
    ) -> None:
        if not isinstance(grace_timer, PlayerDeathGraceTimer):
            raise TypeError("grace_timer must be PlayerDeathGraceTimer")
        # ``append(player_id, output, occurred_at)`` を持つ duck-typed appender
        # を受け取る。Production では ``ObservationAppender`` だが、テストでは
        # MagicMock を渡したいので isinstance ではなく callable 確認に留める。
        if not callable(getattr(observation_appender, "append", None)):
            raise TypeError("observation_appender must expose .append(...)")
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        if not callable(caregiver_name_resolver):
            raise TypeError("caregiver_name_resolver must be callable")
        self._grace_timer = grace_timer
        self._appender = observation_appender
        self._current_tick_provider = current_tick_provider
        self._caregiver_name_resolver = caregiver_name_resolver
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: PlayerRevivedEvent) -> None:
        revived_pid = event.aggregate_id
        prose = self._build_prose(revived_pid, event)
        structured = {
            "kind": "player_revived_post_hoc",
            "caregiver_player_id": (
                int(event.caregiver_player_id)
                if event.caregiver_player_id is not None
                else None
            ),
            "hp_recovered": event.hp_recovered,
            "total_hp": event.total_hp,
        }
        output = ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )
        try:
            self._appender.append(
                player_id=revived_pid,
                output=output,
                occurred_at=datetime.now(timezone.utc),
            )
        except Exception:
            # appender 障害で revive 処理全体を倒さない。Phase 4 で down player
            # の観測を切ったので、ここを silent skip しても他経路から情報が漏れる
            # 心配は無い。ログには残す。
            self._logger.exception(
                "post hoc observation append failed for player_id=%s",
                int(revived_pid),
            )

    def _build_prose(
        self, revived_pid: PlayerId, event: PlayerRevivedEvent,
    ) -> str:
        """post_hoc observation の prose を組み立てる。

        PR-κ (Y_after_pr651_652 分析後続): 復帰した LLM が「travel_to で
        安全な場所へ退避する」判断を下せるよう、event の hp 情報と明示的
        な退避誘導を prose に含める。

        旧 prose: 「{N} tick の間、意識を失っていた。{介抱者} に介抱されて
                   意識が戻った。」

        新 prose: 「... 意識が戻った。（HP {total_hp} まで回復）まだ体は
                   弱っている。ここに脅威が残っているなら travel_to で
                   安全な場所へ移動を検討すること。」

        実 trace (Y_after_pr651_652) で「復帰 → 2 tick 後に再ダウン」のループ
        が観測された。LLM は復帰直後の tick で action turn を得るが、この
        prose を読むだけで「travel_to で逃げるべき」を明示的に認識できる。
        """
        duration_phrase = self._build_duration_phrase(revived_pid)
        caregiver_phrase = self._build_caregiver_phrase(event.caregiver_player_id)
        hp_phrase = f"（HP {event.total_hp} まで回復）"
        warning_phrase = (
            "まだ体は弱っている。ここに脅威 (敵 / 危険地形 / 空腹 100 等) "
            "が残っているなら、travel_to で安全な場所へ移動を検討すること。"
        )
        return (
            f"{duration_phrase}{caregiver_phrase}意識が戻った。"
            f"{hp_phrase} {warning_phrase}"
        )

    def _build_duration_phrase(self, revived_pid: PlayerId) -> str:
        downed_at = self._grace_timer.get_downed_at_tick(revived_pid)
        if downed_at is None:
            # grace_timer に未登録 (想定外: 即時 revive 等) → 時間は不明
            return "数 tick の間、意識を失っていた。"
        try:
            current_tick = int(self._current_tick_provider())
        except Exception:
            self._logger.exception(
                "current_tick_provider raised; falling back to unknown duration"
            )
            return "数 tick の間、意識を失っていた。"
        ticks = max(0, current_tick - downed_at)
        return f"{ticks} tick の間、意識を失っていた。"

    def _build_caregiver_phrase(
        self, caregiver_player_id: Optional[PlayerId]
    ) -> str:
        if caregiver_player_id is None:
            return ""
        resolved = self._caregiver_name_resolver(caregiver_player_id)
        if not resolved:
            resolved = f"Player {int(caregiver_player_id)}"
        return f"{resolved} に介抱されて"

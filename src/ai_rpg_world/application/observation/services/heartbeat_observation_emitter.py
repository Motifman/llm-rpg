"""Idle tick でも LLM エージェントが行動できるようにする合成観測の emitter。

なぜ必要か
-----------
現状の観測駆動アーキテクチャでは、外部からの観測 (移動・会話・干渉) が無い
プレイヤーは LLM ターンが投入されず "停止" した状態になる。MMO 的に複数の
エージェントが共存する世界では、片方が active な間にもう片方が「ぼーっと」
動けないと不自然な硬直が生まれる。

設計
-----
- ``SpotGraphSimulationApplicationService`` の post-tick hook として動作。
  UoW の外なので ``ObservationAppender`` 経由で buffer に直接 append できる。
- LLM プレイヤーごとに「最後に heartbeat を発行した tick」を内部記録し、
  ``interval_ticks`` 経過したら ``schedules_turn=True`` の観測を投入する。
- 既存 ``ObservationTurnScheduler`` が ``schedules_turn`` を見て LLM ターンを
  enqueue し、同じ post-tick hook chain で動く ``ILlmTurnTrigger`` がそれを
  実行する。chain 上、heartbeat emitter は LLM turn trigger より *前* に
  走らせる必要がある。

なぜ最後の実観測 tick を見ない最小実装か
---------------------------------------
「N tick 観測なしなら投入」よりシンプルに「N tick おきに必ず投入」に倒した。
理由:
- 実観測時刻の追跡には ObservationAppender / buffer の側に hook 追加が必要で
  PR スコープを膨らませる
- heartbeat は低刺激な合成観測なので、たとえ実観測と同時に届いても LLM 側
  の判断材料が増えるだけで害は小さい
- 後続 PR で必要になればその時点で「直近観測 tick」を taking する形に拡張可能
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Optional

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)


_DEFAULT_INTERVAL_TICKS = 5
_HEARTBEAT_PROSE = "周囲に大きな変化はない。少し時間が経った。"
_HEARTBEAT_TYPE = "heartbeat"


class HeartbeatObservationEmitter:
    """LLM プレイヤーに ``interval_ticks`` おきに heartbeat 観測を発行する。"""

    def __init__(
        self,
        observation_appender: ObservationAppender,
        turn_scheduler: ObservationTurnScheduler,
        llm_player_ids_provider: Callable[[], Iterable[PlayerId]],
        interval_ticks: int = _DEFAULT_INTERVAL_TICKS,
        time_label_provider: Optional[Callable[[WorldTick], Optional[str]]] = None,
        now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if interval_ticks < 1:
            raise ValueError("interval_ticks must be >= 1")
        self._observation_appender = observation_appender
        self._turn_scheduler = turn_scheduler
        self._llm_player_ids_provider = llm_player_ids_provider
        self._interval_ticks = interval_ticks
        self._time_label_provider = time_label_provider
        self._now_provider = now_provider
        self._last_emitted_tick: dict[int, int] = {}

    def run(self, current_tick: WorldTick) -> None:
        """post-tick hook 本体。各 LLM プレイヤーを巡回し必要なら観測を投入する。"""
        try:
            player_ids = list(self._llm_player_ids_provider())
        except Exception:
            # provider 失敗が tick 全体を倒さないようにする (post-tick hook の責務)
            logger.exception("Failed to enumerate LLM player ids; skipping heartbeat")
            return

        # now / time_label は実際に発行する直前に解決する (anchor tick で
        # 全プレイヤーが skip された場合の無駄な呼び出しを避ける)。
        # time_label は tick 単位なので、最初の emission 時にだけ解決して以降の
        # 同 tick 内では同じ値を共有する。
        now: Optional[datetime] = None
        time_label_resolved = False
        time_label: Optional[str] = None
        for player_id in player_ids:
            if not isinstance(player_id, PlayerId):
                logger.warning(
                    "Skipping non-PlayerId entry from provider: %r", player_id
                )
                continue
            if not self._should_emit(player_id, current_tick):
                continue
            if now is None:
                now = self._now_provider()
            if not time_label_resolved:
                time_label = (
                    self._time_label_provider(current_tick)
                    if self._time_label_provider is not None
                    else None
                )
                time_label_resolved = True
            output = ObservationOutput(
                prose=_HEARTBEAT_PROSE,
                structured={
                    "type": _HEARTBEAT_TYPE,
                    "tick": current_tick.value,
                    "interval_ticks": self._interval_ticks,
                },
                observation_category="environment",
                schedules_turn=True,
            )
            try:
                self._observation_appender.append(
                    player_id, output, now, time_label
                )
            except Exception:
                # append 自体が失敗 → buffer に何も入っていないので next tick
                # で再試行する (= _last_emitted_tick を更新しない)。
                logger.exception(
                    "Heartbeat append failed for player %s", player_id.value
                )
                continue
            # append 成功 = 観測は buffer に乗ったので duplicate を避けるため
            # ここで last_emitted を進める。後続の schedule 失敗とは独立。
            self._last_emitted_tick[player_id.value] = current_tick.value
            try:
                self._turn_scheduler.maybe_schedule(player_id, output)
            except Exception:
                # ターン投入失敗は best-effort: 観測は届いているので次の
                # heartbeat か他観測でリカバーされる。
                logger.exception(
                    "Heartbeat schedule_turn failed for player %s",
                    player_id.value,
                )

    def _should_emit(self, player_id: PlayerId, current_tick: WorldTick) -> bool:
        last = self._last_emitted_tick.get(player_id.value)
        if last is None:
            # 初回は「いま」を基準点として記録するだけで投入はしない。
            # サーバ再起動直後に全プレイヤーが一斉に LLM 呼び出しを行うのを防ぐ。
            self._last_emitted_tick[player_id.value] = current_tick.value
            return False
        return (current_tick.value - last) >= self._interval_ticks

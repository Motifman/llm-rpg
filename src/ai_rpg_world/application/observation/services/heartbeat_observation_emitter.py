"""Per-agent idle timer による heartbeat 観測の emitter。

なぜ必要か
-----------
現状の観測駆動アーキテクチャでは、外部からの観測 (移動・会話・干渉) が無い
プレイヤーは LLM ターンが投入されず "停止" した状態になる。MMO 的に複数の
エージェントが共存する世界では、片方が active な間にもう片方が「ぼーっと」
動けないと不自然な硬直が生まれる。

設計 (#346 Step 3 / #404 後続)
------------------------------
- ``SpotGraphSimulationApplicationService`` の post-tick hook として動作。
  UoW の外なので ``ObservationAppender`` 経由で buffer に直接 append できる。
- **per-agent idle timer**: プレイヤーごとに「最後に活動した tick」を記録し、
  ``interval_ticks`` 経過したときだけ ``schedules_turn=True`` の観測を投入する。
  「活動」は event 駆動でも heartbeat 駆動でも構わない (どちらも
  ``note_player_activity`` で last 更新)。
- 既存 ``ObservationTurnScheduler`` が ``schedules_turn`` を見て LLM ターンを
  enqueue し、同じ post-tick hook chain で動く ``ILlmTurnTrigger`` がそれを
  実行する。chain 上、heartbeat emitter は LLM turn trigger より *前* に
  走らせる必要がある。

旧設計との違い (#346 Step 3 で改修した点)
----------------------------------------
旧: 「N tick おきに必ず投入」(= 最低発火頻度のフロア)。event 駆動でターンを
    回した直後の player にも N tick 後に冗長な heartbeat が届いていた。
新: 「N tick 何も無ければ投入」(= 最大沈黙時間の天井)。LLM turn trigger が
    ``note_player_activity`` を呼んで last を更新するため、active な player は
    event 駆動だけで動き続け heartbeat が出ない。

#404 で発見された wall time スパイク (1 driver iteration で N 倍の
LLM 呼び出し) の構造的原因の 1 つを除去する。
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


_DEFAULT_INTERVAL_TICKS = 6
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
        is_traveling_provider: Optional[Callable[[PlayerId], bool]] = None,
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
        # #404 fix: 移動中の player には heartbeat を発行しない。
        # 旧実装は heartbeat 観測 → schedules_turn=True → 移動中でも
        # LLM ターンが走る → 「移動中なのに何かしようとして失敗」が連発する
        # silent failure 経路だった。is_traveling_provider が None なら
        # 従来通りの全員一斉発火 (後方互換)。
        self._is_traveling_provider = is_traveling_provider

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
            # #404 fix: 移動中なら heartbeat 自体を投入しない。schedules_turn
                # で起こさない上に、観測 buffer にも残さない (LLM プロンプトに
                # 「いま heartbeat が来た」と読まれて行動誘発するのを防ぐ)。
            if self._is_traveling_provider is not None:
                try:
                    if self._is_traveling_provider(player_id):
                        continue
                except Exception:
                    # provider 失敗は fail-safe で従来通り emit する
                    logger.exception(
                        "is_traveling_provider failed for player %s; emitting heartbeat anyway",
                        player_id.value,
                    )
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

    def note_player_activity(
        self, player_id: PlayerId, current_tick: WorldTick
    ) -> None:
        """player が tick T で行動した、と emitter に伝える (#346 Step 3 本体)。

        per-agent idle timer の意味論を成立させるためのフック。LLM turn trigger
        が turn 完了直後に呼ぶと、event 駆動で動いている active な player に
        対しては heartbeat が ``interval_ticks`` 後まで再発火しなくなる。

        旧 emitter ("N tick おきに必ず発火する floor") を本メソッドで
        "N tick 沈黙が続いたときだけ発火する ceiling" に変える。turn trigger と
        emitter を別 PR で分離しておくため、wiring 上は emitter を持つ runtime
        側から trigger に渡す形を取る。
        """
        if not isinstance(player_id, PlayerId):
            return
        # _should_emit と同じキー (player_id.value) で last を上書きする。
        # heartbeat の次回判定は (current - last) >= interval_ticks なので、
        # ここで last = current にしておけば次の heartbeat は最短で
        # current + interval_ticks 後。
        self._last_emitted_tick[player_id.value] = current_tick.value

    def forget_player(self, player_id: PlayerId) -> None:
        """指定プレイヤーの内部状態を破棄する (session 終了時呼ばれる想定)。"""
        self._last_emitted_tick.pop(player_id.value, None)

    def prune_inactive(self, active_player_ids: "Iterable[PlayerId]") -> int:
        """``active_player_ids`` に含まれないプレイヤーの記録を一括削除する。

        long-running サーバでセッションが回転していくと
        ``_last_emitted_tick`` が無制限に増大する。提供者側 (例:
        ``GameRuntimeManager`` のセッション cleanup hook) からアクティブな
        プレイヤー集合を渡してもらい、それ以外を破棄するためのヘルパー。
        戻り値は削除件数。
        """
        active = {pid.value for pid in active_player_ids}
        stale = [pid for pid in self._last_emitted_tick.keys() if pid not in active]
        for pid in stale:
            del self._last_emitted_tick[pid]
        return len(stale)

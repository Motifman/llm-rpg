"""LLM turn のスケジューリングと Phase A/B 並列実行。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import WorldLlmWiring

logger = logging.getLogger(__name__)

@dataclass
class WorldLlmTurnTrigger:
    """Queues LLM turns and runs them against the session runtime.

    ## 「turn」「ターン」という言葉について

    本クラスの ``run_scheduled_turns`` / ``schedule_turn`` の "turn" は
    **TRPG の順番待ち** の意味では **無い**。実体は event 駆動の wave
    実行: 1 world tick = 1 wave、 wave 内で ``pending_player_ids`` の
    全員を並列に LLM 呼び出しする。

    ## ``_self_reschedule_streak`` の責務 (= 旧名 ``_turn_counts``)

    **「自分の ``result.should_reschedule=True`` で繰り返し起床する
    self-loop チェイン」の連続数を ``max_self_reschedule_streak`` で
    打ち切る** ためのカウンタ。**他者観測 / 失敗通知 / arrival callback
    等の外部起床 (= schedule_turn 経由) は streak を触らない** ので、
    ping-pong (= A↔B が互いに発話で起こし合う相互作用) は無限に許容する
    (= 自然な振る舞いなので止めない)。

    chain を終了させる条件:
    - ``was_no_op=True`` (= LLM が tool を返さなかった)
    - ``should_reschedule=False`` (= 通常成功 or reschedule 不要な失敗)
    - streak が ``max_self_reschedule_streak`` に到達 (= self-loop の強制 stop)

    旧名 ``max_turns`` / ``_turn_counts`` は「TRPG ターン上限」を連想させて
    誤読を招いていたため、PR-I で意味を反映した名前に変更した。

    ## PR-I の挙動変化 (意図的)

    1. ``schedule_turn`` が ``_self_reschedule_streak`` を一切触らない
       (旧: ``setdefault(pid, 0)`` で「未登録なら 0 を入れる」をしていたが、
       外部起床経路は self-loop chain と独立であるべきという原則に合わせて
       撤廃)
    2. 旧 ``_account_result`` の ``elif should_reschedule or current_count < max_turns``
       が含意していた「**should_reschedule に関わらず max ターンまで auto-stay**」
       挙動を撤廃。新コードは ``should_reschedule=True`` の時だけ streak を
       積んで pending に再追加する。``should_reschedule=False`` (= 通常成功 or
       reschedule 不要な失敗) は即 chain 終了 = streak pop。

    ## 1. の影響範囲

    ``schedule_turn`` は他者観測 / arrival callback / idle timer が呼ぶ経路で、
    self-loop chain (= 同一 agent 自走) とは独立。streak を触らないことで
    ping-pong (= A↔B の発話で起こし合う相互作用) が永続的に成立する。

    ## 2. の影響範囲

    調査済み: ``should_reschedule=True`` を実際に返す経路は
    ``_RESCHEDULE_ERROR_CODES`` に明示された API 一時失敗・名前解決失敗・
    修正可能な interaction 失敗のみ。
    通常成功は ``should_reschedule=False`` がデフォルト。よって「auto-stay 5
    turns に暗黙的に依存するコード」は事実上存在せず、本変更は実走の挙動を
    変えない。Y 実走で観測された「**player 1 が 75 wave 連続活動**」は
    auto-stay の副産物ではなく **外部観測連鎖**による正当な活動だったので、
    新コードでも同じパターンが再現する。
    """

    wiring: "WorldLlmWiring"
    # 自己 reschedule チェインの連続上限。これに達したら pending から外す。
    # 他者観測経由の起床は影響を受けないので、ping-pong は影響なし。
    max_self_reschedule_streak: int = 5
    pending_player_ids: set[int] = field(default_factory=set)
    # 旧名 _turn_counts。pid → 自己 reschedule の連続回数。
    _self_reschedule_streak: dict[int, int] = field(default_factory=dict)

    def schedule_turn(self, player_id: PlayerId) -> None:
        """外部要因 (他者観測 / arrival / idle timer 等) による起床。

        **``_self_reschedule_streak`` には触らない**。これにより:
        - ping-pong (= 他者発話で起こし合う) は streak を 0 リセットせず、
          かつ streak を増やしもしないので、永続的に成立する
        - self-loop の streak (= 既に積まれていた値) も保持される。次の
          turn で should_reschedule=True なら +1 して累積する
        - pop 済 pid に対しては未登録扱い、次の self-reschedule で 1 から
          数え直す (= ``_self_reschedule_streak.get(pid, 0)`` の default 経由)
        """
        self.pending_player_ids.add(player_id.value)

    def run_scheduled_turns(self) -> None:
        # #363 Fix 1a: ゲーム既終了なら一切 LLM を回さない。実験 #25 ON_FULL で
        # 全員 DEAD 後も LLM ターン継続 → 駆動 tick 107 が 49 分ハングした
        # silent failure を防ぐ。check_game_end() は all_resolved() で O(N)、
        # 毎 tick 叩いても問題ない軽さ。
        runtime = self.wiring.runtime
        check_game_end = getattr(runtime, "check_game_end", None)
        if callable(check_game_end):
            try:
                if check_game_end().is_ended:
                    self.pending_player_ids.clear()
                    self._self_reschedule_streak.clear()
                    return
            except Exception:
                # check_game_end 自体が落ちても turn 実行を続ける fail-safe
                logger.exception("check_game_end raised; continuing turn execution")

        to_run = list(self.pending_player_ids)
        self.pending_player_ids.clear()
        # #363 Fix 1b: 行動不可 (is_down / outcome 確定) のプレイヤーを除外。
        # 死亡したプレイヤーが speech 観測などで起こされるケースがあるため、
        # to_run の filter は確実に必要。
        to_run = [pid for pid in to_run if self._can_player_act(pid)]
        if not to_run:
            return

        cfg = getattr(runtime, "_runtime_config", None)
        workers = int(getattr(cfg, "llm_turn_parallel_workers", 0) or 0)
        # 比較 run で会議を一人ずつ発言させる場合だけ、同じ world tick の
        # 先行発言を後続者の prompt へ入れる。既定は実時間を守る並列で、
        # 自由時間は設定にかかわらず wave の同時性を維持する。
        if bool(getattr(cfg, "llm_meeting_serial_turns", False)) and (
            runtime._game_phase_store.is_meeting()
        ):
            workers = 1
        if workers <= 1 or len(to_run) <= 1:
            # 旧シリアル経路: 並列化を OFF にした / プレイヤーが 1 人だけ。
            # 完全に従来挙動。
            for player_id_value in to_run:
                result = self.wiring.run_turn(PlayerId(player_id_value))
                self._account_result(player_id_value, result)
            return

        # 並列 Phase A: 各プレイヤーの prompt 構築 + LLM 呼び出しを ThreadPool
        # で同時実行する。litellm.completion はブロッキング HTTP なので、
        # CPython の GIL を解放して並列に走る。
        # 制約: build_full_prompt は observation buffer を drain するが、
        # buffer は player_id keyed の dict なので別プレイヤー間で衝突しない。
        max_workers = min(workers, len(to_run))
        phase_a_results: dict[int, LlmPhaseAResult] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.wiring.run_phase_a, PlayerId(pid_value)
                ): pid_value
                for pid_value in to_run
            }
            for future in futures:
                pid_value = futures[future]
                # 例外は Phase A 内で捕まえて LlmPhaseAResult.exception に
                # 詰めてあるので、future.result() がさらに raise することは
                # 基本ない (Defense-in-depth で try/except)。
                try:
                    phase_a_results[pid_value] = future.result()
                except Exception as exc:
                    logger.exception(
                        "Phase A failed for player_id=%s", pid_value
                    )
                    phase_a_results[pid_value] = LlmPhaseAResult(
                        player_id=PlayerId(pid_value),
                        prompt={},
                        tools_payload=[],
                        tool_call=None,
                        exception=exc,
                    )

        # Phase B は serial: to_run 順に世界 mutation を適用する。
        # 観測 broadcast / trace recording の順序も to_run 順で確定する。
        for pid_value in to_run:
            phase_a = phase_a_results.get(pid_value)
            if phase_a is None:
                continue
            result = self.wiring.run_phase_b(phase_a)
            self._account_result(pid_value, result)

    def _account_result(
        self, player_id_value: int, result: LlmCommandResultDto
    ) -> None:
        """turn 完了後の self-reschedule streak 管理を 1 か所に集約する。

        chain を終わらせる条件:
        - ``result.was_no_op``: LLM が tool を返さなかった (= chain 中断)
        - ``result.should_reschedule=False``: 通常成功 or reschedule 不要な
          失敗 (= self-loop ではない)
        - streak が ``max_self_reschedule_streak`` に到達: self-loop の
          強制 stop

        chain を継続する条件:
        - ``result.should_reschedule=True`` かつ streak が未到達 → streak +1
          して pending に再追加
        """
        current_streak = self._self_reschedule_streak.get(player_id_value, 0) + 1
        if result.was_no_op:
            # tool を返さなかった = chain 中断
            self._self_reschedule_streak.pop(player_id_value, None)
        elif not result.should_reschedule:
            # 通常成功 or reschedule 不要な失敗 = chain 終了
            self._self_reschedule_streak.pop(player_id_value, None)
        elif current_streak >= self.max_self_reschedule_streak:
            # 上限到達: chain を強制終了して streak を pop (= 次回 fresh start)。
            # **pending には触らない**: 同 wave で他者観測経由で
            # schedule_turn された外部起床を消さないため。
            # 結果として:
            #   - 同 wave で外部観測があれば次 wave で走る (= 外部起床は妨げない)
            #   - 外部観測が無ければ次 wave で走らない (= 自走 chain は止まる)
            #   - 次回 should_reschedule=True を返した時は streak=1 からの新しい
            #     chain として数え直す (= soft cap)
            self._self_reschedule_streak.pop(player_id_value, None)
        else:
            # should_reschedule=True かつ未到達 → streak を累積して chain 継続
            self._self_reschedule_streak[player_id_value] = current_streak
            self.pending_player_ids.add(player_id_value)
        # #346 Step 3 / #404: per-agent idle timer の last 更新。turn が走った
        # = 「いま活動した」なので heartbeat の沈黙タイマーをリセットする。
        # event 駆動で頻繁に動く player には heartbeat が出なくなり、
        # 完全 idle な player だけ idle_timeout 経過後に 1 回起こされる。
        self._note_activity_after_turn(player_id_value)
        # #526 / U3: 段1 エピソード再解釈の trigger 後半。turn 完了を coordinator に
        # 通知し、interval 到達時に pending recall batch を LLM 再解釈する。
        # reinterpretation OFF (coordinator 未構築) では no-op。
        self._note_turn_for_reinterpretation(player_id_value)
        # U3b: 固着パス。turn 完了を coordinator に通知し、発火条件
        # (interval 到達 / cue_signature 反復 / salience=high) を満たした
        # ときだけ evidence batch を belief journal に統合する。
        # BELIEF_CONSOLIDATION_ENABLED OFF (coordinator 未構築) では no-op。
        self._note_turn_for_belief_consolidation(player_id_value)
        # PR-T: 次回 prompt の「身体の状態」差分表示用に need 値を snapshot する。
        # 「前回の自分のターン終了時 → 次回 prompt」までの変化が delta として
        # 表示される (= 自然 decay + 他者観測の影響 + own action 結果)。
        self._snapshot_needs_after_turn(player_id_value)
        self.wiring.short_term_memory.complete_turn(PlayerId(player_id_value))

    def _snapshot_needs_after_turn(self, player_id_value: int) -> None:
        """PR-T: turn 終了時に当該 player の現在 need 値を「前回」として保存する
        fail-safe ヘルパ。次回 turn の prompt build で diff 表示に使われる。
        """
        runtime = self.wiring.runtime
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            return
        try:
            player_status = repo.find_by_id(PlayerId(player_id_value))
            if player_status is not None and hasattr(
                player_status, "snapshot_needs_for_delta"
            ):
                player_status.snapshot_needs_for_delta()
                # HP の前 turn baseline も同じタイミングで更新する。次 turn の
                # 「身体の状態」section で HP 増減 (前回 -12 等) を出すため。
                if hasattr(player_status, "snapshot_hp_for_delta"):
                    player_status.snapshot_hp_for_delta()
                repo.save(player_status)
        except Exception:
            # snapshot 精度低下は致命ではない (差分が 0 になるだけ)
            logger.warning(
                "snapshot_needs_for_delta failed for player_id=%s",
                player_id_value,
                exc_info=True,
            )

    def _note_turn_for_reinterpretation(self, player_id_value: int) -> None:
        """reinterpretation coordinator に turn 完了を通知する fail-safe ヘルパ。

        coordinator 未配線 (reinterpretation OFF) / 異常系では何もしない
        (turn 実行自体は壊さない)。``_note_activity_after_turn`` と同じ方式。
        """
        stack = getattr(self.wiring.runtime, "_episodic_stack", None)
        coordinator = (
            getattr(stack, "reinterpretation_coordinator", None) if stack else None
        )
        if coordinator is None:
            return
        player_id = PlayerId(player_id_value)
        acting = self.wiring.runtime._acting_being_for(player_id)
        if acting is None:
            return
        try:
            coordinator.after_turn_completed(player_id, acting.being_id)
        except Exception:
            # 再解釈の失敗は致命ではない (worst case: 再解釈が進まないだけ)。
            logger.warning(
                "reinterpretation after_turn_completed failed for player=%s",
                player_id_value,
                exc_info=True,
            )

    def _note_turn_for_belief_consolidation(self, player_id_value: int) -> None:
        """固着パス coordinator に turn 完了を通知する fail-safe ヘルパ。

        coordinator 未配線 (BELIEF_CONSOLIDATION_ENABLED OFF) / 異常系では
        何もしない (turn 実行自体は壊さない)。
        ``_note_turn_for_reinterpretation`` と同じ方式。
        """
        stack = getattr(self.wiring.runtime, "_episodic_stack", None)
        coordinator = (
            getattr(stack, "belief_consolidation_coordinator", None) if stack else None
        )
        if coordinator is None:
            return
        player_id = PlayerId(player_id_value)
        acting = self.wiring.runtime._acting_being_for(player_id)
        if acting is None:
            return
        try:
            coordinator.after_turn_completed(player_id, acting.being_id)
        except Exception:
            # 固着の失敗は致命ではない (worst case: 学びが固着しないだけ)。
            logger.warning(
                "belief consolidation after_turn_completed failed for player=%s",
                player_id_value,
                exc_info=True,
            )

    def _note_activity_after_turn(self, player_id_value: int) -> None:
        """heartbeat emitter に「player が今ターン走った」を通知する fail-safe ヘルパ。

        emitter 未配線 / 異常系では何もしない (turn 実行自体は壊さない)。
        """
        runtime = self.wiring.runtime
        emitter = None
        sim = getattr(runtime, "_simulation_service", None)
        if sim is not None:
            emitter = getattr(sim, "_heartbeat_emitter", None)
        if emitter is None or not hasattr(emitter, "note_player_activity"):
            return
        try:
            current = int(runtime.current_tick())
            emitter.note_player_activity(
                PlayerId(player_id_value), WorldTick(current)
            )
        except Exception:
            # idle timer の精度低下は致命ではない (worst case 旧来挙動)
            logger.warning(
                "note_player_activity failed for player_id=%s",
                player_id_value,
                exc_info=True,
            )

    def _can_player_act(self, player_id_value: int) -> bool:
        """#363 Fix 1b: 行動不可なプレイヤーを LLM 経路から除外する。

        判定:
        - outcome 確定 (EJECTED / RESCUED / STRANDED) → 行動不可
        - DEAD はシナリオで去った主体が有効な場合だけ行動可
        - is_down (= can_act() False) → 行動不可
        - 上記いずれも当たらない / 情報不足 → 行動可 (fail-safe で turn を回す)

        実験 #25 ON_FULL では死亡後も speech 観測等で起こされて LLM ターン
        が継続し、駆動 tick が膨張した。filter を入れて死亡 player を skip。
        """
        runtime = self.wiring.runtime
        if not runtime._player_life_query.can_take_turn(
            PlayerId(player_id_value)
        ):
            return False
        # 移動中の抑止は生死の問いではないため、この入口に残す。
        status_repo = getattr(runtime, "_player_status_repo", None)
        if status_repo is None:
            return True
        try:
            status = status_repo.find_by_id(PlayerId(player_id_value))
            if status is None:
                return True
            # #404 fix: 移動中 (is_traveling=True) の player は LLM ターンを
            # 回さない。意味論として「移動中は次の意思決定をしない」が自然で、
            # かつ heartbeat / observation で起こされても turn 実行を空回り
            # させない。到着時に SpotGraphTravelStageService.on_arrival
            # 経由で schedule_turn が打たれて再開する。
            nav = status.spot_navigation_state
            if nav is not None and nav.is_traveling:
                return False
            return True
        except Exception:
            logger.warning(
                "player_status_repo.find_by_id failed for player_id=%s; "
                "falling back to turn-continue", player_id_value,
                exc_info=True,
            )
            return True

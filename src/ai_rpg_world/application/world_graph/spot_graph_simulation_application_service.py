"""スポットグラフモード用のワールドティック（2D シミュレーションの軽量版）。"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.exceptions import (
    SpotGraphPostTickHookFailedException,
    SpotGraphSimulationException,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import SpotGraphTravelStageService
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
    from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
        HeartbeatObservationEmitter,
    )


class SpotGraphSimulationApplicationService:
    """スポットグラフ上のゲームループ（時間進行・継続移動・任意で LLM トリガ）。"""

    def __init__(
        self,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
        travel_stage: Optional[SpotGraphTravelStageService] = None,
        scenario_event_stage: Optional["_SpotGraphTickStage"] = None,
        reactive_binding_stage: Optional["_SpotGraphTickStage"] = None,
        reactive_object_state_stage: Optional["_SpotGraphTickStage"] = None,
        sync_action_resolver_stage: Optional["_SpotGraphTickStage"] = None,
        environment_stage: Optional["_SpotGraphTickStage"] = None,
        day_night_stage: Optional["_SpotGraphTickStage"] = None,
        needs_decay_stage: Optional["_SpotGraphTickStage"] = None,
        monster_spawn_stage: Optional["_SpotGraphTickStage"] = None,
        monster_behavior_stage: Optional["_SpotGraphTickStage"] = None,
        food_spoilage_stage: Optional["_SpotGraphTickStage"] = None,
        outcome_resolution_stage: Optional["_SpotGraphTickStage"] = None,
        death_grace_stage: Optional["_SpotGraphTickStage"] = None,
        status_effects_stage: Optional["_SpotGraphTickStage"] = None,
        llm_turn_trigger: Optional["ILlmTurnTrigger"] = None,
        heartbeat_emitter: Optional["HeartbeatObservationEmitter"] = None,
        graph_event_flusher: Optional[Callable[[], None]] = None,
    ) -> None:
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._travel_stage = travel_stage
        self._scenario_event_stage = scenario_event_stage
        self._reactive_binding_stage = reactive_binding_stage
        self._reactive_object_state_stage = reactive_object_state_stage
        self._sync_action_resolver_stage = sync_action_resolver_stage
        self._environment_stage = environment_stage
        self._day_night_stage = day_night_stage
        self._needs_decay_stage = needs_decay_stage
        self._monster_spawn_stage = monster_spawn_stage
        self._monster_behavior_stage = monster_behavior_stage
        self._food_spoilage_stage = food_spoilage_stage
        self._outcome_resolution_stage = outcome_resolution_stage
        # Issue #621: ダウン後 30 tick 経過判定。outcome_resolution_stage は
        # 「RESCUED / STRANDED の地理 / 時間 判定」、death_grace_stage は
        # 「DEAD の grace 期限判定」。両者は独立だが、同 tick 内で
        # death_grace_stage を **後** に置くことで「同 tick で revive されたら
        # DEAD 確定をスキップする」順序を保つ (= 救援 event handler が
        # set_outcome(RESCUED) を呼ぶ可能性は今は無いが、将来 RESCUED handler
        # が grace_timer.cancel するなら順序が効く)。
        self._death_grace_stage = death_grace_stage
        self._status_effects_stage = status_effects_stage
        self._llm_turn_trigger = llm_turn_trigger
        self._heartbeat_emitter = heartbeat_emitter
        # PR-N (task #30): tick stage で graph.add_event された events を
        # observation pipeline 経由で flush するための hook。interaction /
        # speech 経路でしか _process_graph_events() が呼ばれない silent
        # failure を heartbeat tick でも止める。world_runtime 構築時に
        # ``self._process_graph_events`` が渡される想定。
        self._graph_event_flusher = graph_event_flusher
        self._logger = logging.getLogger(self.__class__.__name__)

    def tick(self) -> WorldTick:
        """1 ティック進める（UoW 内で時間とスポット間移動を処理し、フックはトランザクション外）。"""
        return self._execute_with_error_handling(
            operation=self._tick_impl,
            context={"action": "spot_graph_tick"},
        )

    def set_llm_turn_trigger(
        self, trigger: Optional["ILlmTurnTrigger"]
    ) -> None:
        """プレゼン層などから、ティック後に走らせる LLM トリガを差し替える（主に脱出デモ）。"""
        self._llm_turn_trigger = trigger

    def set_heartbeat_emitter(
        self, emitter: Optional["HeartbeatObservationEmitter"]
    ) -> None:
        """ティック後の heartbeat emitter を注入する（脱出デモなどプレゼン層から）。"""
        self._heartbeat_emitter = emitter

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            current_tick = self._time_provider.advance_tick()
            if self._travel_stage is not None:
                self._travel_stage.run(current_tick)
            if self._scenario_event_stage is not None:
                self._scenario_event_stage.run(current_tick)
            if self._reactive_object_state_stage is not None:
                # Issue #188 Step 3: passage より先に object state を評価する。
                # 旧順序 (passage → object) では、object state の変化 (例:
                # 「制御室から人が居なくなって power_on=false」) が、同 tick の
                # passage 評価に反映されず 1 tick の grace period を生んでいた。
                # この timing exploit は relay_puzzle で operator が「黙って
                # 制御室を離れて vault に駆け込む」抜け道として悪用されうる。
                # 新順序 (object → passage) では、object state 変化が即 passage
                # 評価に反映され、因果として自然な「object が変わったら passage
                # が連動する」挙動になる。
                # latch mechanism (Step 2) が正規の relay 解法を提供するので、
                # この順序変更で scenario は依然解ける。
                self._reactive_object_state_stage.run(current_tick)
            if self._reactive_binding_stage is not None:
                # scenario_event の flag 更新 + reactive_object の object state
                # 更新を同 tick で読みたいので、両者の後に走らせる。
                self._reactive_binding_stage.run(current_tick)
            if self._sync_action_resolver_stage is not None:
                # sync group の判定はその tick の prepare（ツール実行で
                # 既に flag 化されている）を見るため、reactive 反映の
                # 後で走らせる。完成 / タイムアウトに伴う on_complete /
                # on_timeout 効果は次ステージ以降に伝搬する。
                self._sync_action_resolver_stage.run(current_tick)
            if self._environment_stage is not None:
                self._environment_stage.run(current_tick)
            if self._day_night_stage is not None:
                # environment_stage 後に走らせる: 仮に将来「天候が夜だけ強くなる」
                # のような相互作用が必要になっても、weather → time_of_day の
                # 順序で組み立てれば一貫した state が得られる。今は両者独立。
                self._day_night_stage.run(current_tick)
            if self._needs_decay_stage is not None:
                self._needs_decay_stage.run(current_tick)
            if self._status_effects_stage is not None:
                # PR #2: active status effect の継続適用 + 期限切れ掃除。
                # needs_decay の後に置いて、空腹からの BLEEDING 発症などの
                # 連鎖を同 tick 内で処理しやすくする。HP 0 で DEAD outcome
                # 連鎖は E-3a の handler に任せる (publisher 経由)。
                self._status_effects_stage.run(current_tick)
            if self._monster_spawn_stage is not None:
                # 動的 spawn / despawn 判定。day_night / weather / flag を
                # 評価し、条件付きスロットを必要に応じてスポーン or デスポーン。
                # behavior の前に走らせることで「その tick で spawn したモンスター
                # が同 tick の behavior に乗る」。
                self._monster_spawn_stage.run(current_tick)
            if self._monster_behavior_stage is not None:
                # モンスター行動 tick: attack / wander / pack 行動。
                # needs_decay 後に置くことで「同 tick でモンスターが空腹を
                # 感じてから行動を決める」順序になる (将来の forage 連動)。
                self._monster_behavior_stage.run(current_tick)
            if self._food_spoilage_stage is not None:
                # Phase D-2: 食料腐敗判定。pure な item state mutation で
                # tick 内の他 stage と依存しないが、観測 callback を持つ可能性
                # を考えて post_tick_hooks の前に commit に乗せる。
                # 順序は他 stage 後で OK: 同 tick で gather → spoilage 判定 されても
                # acquired_at_tick が今回 tick で初期化されるだけで、閾値到達は
                # 次回以降。
                self._food_spoilage_stage.run(current_tick)
            if self._outcome_resolution_stage is not None:
                # Phase E-3b: プレイヤー個別 outcome の RESCUED/STRANDED 判定。
                # 当 tick の travel / interaction が反映された後に走らせる
                # ことで、「同 tick で summit に着いた → そのまま救助される」
                # の自然な流れを実現する。DEAD は別経路 (PlayerDownedEvent
                # ハンドラ) で確定するので、こちらは時間ベースの判定のみ。
                self._outcome_resolution_stage.run(current_tick)
            if self._death_grace_stage is not None:
                # Issue #621: ダウン後 30 tick 経過した player を DEAD 確定。
                # outcome_resolution_stage の **後** に置くことで、同 tick で
                # RESCUED 確定した player に対する DEAD 上書きを set_outcome
                # の冪等で防ぐ (= 順序が逆だと DEAD → RESCUED 試行で no-op)。
                self._death_grace_stage.run(current_tick)
        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        failures: list[tuple[str, Exception]] = []
        # 順序が重要:
        #   graph_event_flusher → heartbeat → llm_turn_trigger。
        # PR-N: graph_event_flusher を heartbeat より先に走らせる。tick stage
        # (= monster_behavior / status_effects / needs_decay) で graph に
        # 積まれた events を flush して観測 pipeline に流すと、その観測の
        # schedules_turn=True が heartbeat より先に turn を積む → turn_trigger
        # が拾える。逆順だと heartbeat 後の turn 実行までに events が
        # 観測 buffer に届かない silent failure になる。
        hooks = (
            (
                "graph_event_flusher",
                self._graph_event_flusher,
                lambda hook: hook(),
            ),
            (
                "heartbeat_emitter",
                self._heartbeat_emitter,
                lambda hook: hook.run(current_tick),
            ),
            (
                "llm_turn_trigger",
                self._llm_turn_trigger,
                lambda hook: hook.run_scheduled_turns(),
            ),
        )
        for hook_name, hook, runner in hooks:
            if hook is None:
                continue
            try:
                runner(hook)
            except Exception as exc:  # post-commit hook なので残りも実行して失敗を集約する
                self._logger.exception(
                    "Spot graph post-tick hook failed",
                    extra={"hook_name": hook_name, "tick": current_tick.value},
                )
                failures.append((hook_name, exc))
        if failures:
            raise SpotGraphPostTickHookFailedException(
                current_tick=current_tick,
                failed_hooks=tuple(name for name, _ in failures),
                original_exception=failures[0][1],
            )

    def _execute_with_error_handling(self, operation, context: dict) -> WorldTick:
        try:
            return operation()
        except ApplicationException:
            raise
        except DomainException as exc:
            raise SpotGraphSimulationException(str(exc), cause=exc, **context) from exc
        except Exception as exc:
            self._logger.error(
                "Unexpected error in spot graph simulation",
                extra={**context, "error": str(exc)},
            )
            raise SystemErrorException(
                f"{context.get('action', 'spot_graph_tick')} failed: {str(exc)}",
                original_exception=exc,
            ) from exc


__all__ = ["SpotGraphSimulationApplicationService"]


class _SpotGraphTickStage(Protocol):
    def run(self, current_tick: WorldTick) -> None: ...

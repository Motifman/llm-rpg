"""スポットグラフモード用のワールドティック（2D シミュレーションの軽量版）。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.exceptions import (
    SpotGraphPostTickHookFailedException,
    SpotGraphSimulationException,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import SpotGraphTravelStageService
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import WorldTickFailureIsolator
from ai_rpg_world.domain.common.exception import DomainException
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
        travel_stage: SpotGraphTravelStageService | None = None,
        scenario_event_stage: _SpotGraphTickStage | None = None,
        reactive_binding_stage: _SpotGraphTickStage | None = None,
        reactive_object_state_stage: _SpotGraphTickStage | None = None,
        sync_action_resolver_stage: _SpotGraphTickStage | None = None,
        environment_stage: _SpotGraphTickStage | None = None,
        day_night_stage: _SpotGraphTickStage | None = None,
        needs_decay_stage: _SpotGraphTickStage | None = None,
        monster_spawn_stage: _SpotGraphTickStage | None = None,
        monster_behavior_stage: _SpotGraphTickStage | None = None,
        food_spoilage_stage: _SpotGraphTickStage | None = None,
        player_outcome_rule_stage: _PlayerOutcomeRuleTickStage | None = None,
        death_grace_stage: _SpotGraphTickStage | None = None,
        trade_offer_expiry_stage: _SpotGraphTickStage | None = None,
        market_order_expiry_stage: _SpotGraphTickStage | None = None,
        status_effects_stage: _SpotGraphTickStage | None = None,
        llm_turn_trigger: ILlmTurnTrigger | None = None,
        heartbeat_emitter: HeartbeatObservationEmitter | None = None,
        graph_event_flusher: Callable[[], None] | None = None,
        failure_isolator: WorldTickFailureIsolator | None = None,
    ) -> None:
        self._time_provider = time_provider
        self._failure_isolator = failure_isolator or WorldTickFailureIsolator.fail_fast()
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
        self._player_outcome_rule_stage = player_outcome_rule_stage
        # Issue #621: ダウン後 30 tick 経過判定。player_outcome_rule_stage は
        # 「宣言された個人結果規則の判定」、death_grace_stage は
        # 「DEAD の grace 期限判定」。両者は独立だが、同 tick 内で
        # death_grace_stage を **後** に置くことで「同 tick で revive されたら
        # DEAD 確定をスキップする」順序を保つ (= 救援 event handler が
        # set_outcome(RESCUED) を呼ぶ可能性は今は無いが、将来 RESCUED handler
        # が grace_timer.cancel するなら順序が効く)。
        self._death_grace_stage = death_grace_stage
        # 経済統合 Phase 2: 返事のないまま期限を過ぎた取引の片付け。
        # player_outcome_rule_stage の直前に置く (下の _tick_impl 参照)。
        self._trade_offer_expiry_stage = trade_offer_expiry_stage
        # 経済統合 Phase 3: 期限を過ぎた板の注文の片付け。
        self._market_order_expiry_stage = market_order_expiry_stage
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
        """1ティック進め、stageを宣言順に実行してから確定後フックを呼ぶ。"""
        return self._execute_with_error_handling(
            operation=self._tick_impl,
            context={"action": "spot_graph_tick"},
        )

    def set_llm_turn_trigger(self, trigger: ILlmTurnTrigger | None) -> None:
        """プレゼン層などから、ティック後に走らせる LLM トリガを差し替える（主に脱出デモ）。"""
        self._llm_turn_trigger = trigger

    def set_heartbeat_emitter(self, emitter: HeartbeatObservationEmitter | None) -> None:
        """ティック後の heartbeat emitter を注入する（脱出デモなどプレゼン層から）。"""
        self._heartbeat_emitter = emitter

    def _tick_impl(self) -> WorldTick:
        # world tickは処理順序を与えるcoordinatorであり、tick全体のtransaction
        # ではない。各stageまたはその内側のcommandが自分の確定境界を持つ。
        # 途中stageが失敗しても、既に確定した前段を巻き戻して同じtickを再実行
        # すると二重適用になるため、時刻は先に一度だけ進めて戻さない。
        current_tick = self._time_provider.advance_tick()
        if self._travel_stage is not None:
            self._run_stage("travel", self._travel_stage, current_tick)
        if self._scenario_event_stage is not None:
            self._run_stage("scenario_event", self._scenario_event_stage, current_tick)
        if self._reactive_object_state_stage is not None:
            # Issue #188 Step 3: passage より先に object state を評価する。
            # 旧順序 (passage → object) では、object state の変化 (例:
            # 「制御室から人が居なくなって power_on=false」) が、同 tick の
            # passage 評価に反映されず 1 tick の grace period を生んでいた。
            # この timing exploit は relay_puzzle (#1631 で退役) で operator が
            # 「黙って制御室を離れて vault に駆け込む」抜け道として悪用されえた。
            # 新順序 (object → passage) では、object state 変化が即 passage
            # 評価に反映され、因果として自然な「object が変わったら passage
            # が連動する」挙動になる。
            self._run_stage("reactive_object_state", self._reactive_object_state_stage, current_tick)
        if self._reactive_binding_stage is not None:
            # scenario_event の flag 更新 + reactive_object の object state
            # 更新を同 tick で読みたいので、両者の後に走らせる。
            self._run_stage("reactive_binding", self._reactive_binding_stage, current_tick)
        if self._sync_action_resolver_stage is not None:
            # sync group の判定はその tick の prepare（ツール実行で
            # 既に flag 化されている）を見るため、reactive 反映の
            # 後で走らせる。完成 / タイムアウトに伴う on_complete /
            # on_timeout 効果は次ステージ以降に伝搬する。
            self._run_stage("sync_action_resolver", self._sync_action_resolver_stage, current_tick)
        if self._environment_stage is not None:
            self._run_stage("environment", self._environment_stage, current_tick)
        if self._day_night_stage is not None:
            # environment_stage 後に走らせる: 仮に将来「天候が夜だけ強くなる」
            # のような相互作用が必要になっても、weather → time_of_day の
            # 順序で組み立てれば一貫した state が得られる。今は両者独立。
            self._run_stage("day_night", self._day_night_stage, current_tick)
        if self._needs_decay_stage is not None:
            self._run_stage("needs_decay", self._needs_decay_stage, current_tick)
        if self._status_effects_stage is not None:
            # PR #2: active status effect の継続適用 + 期限切れ掃除。
            # needs_decay の後に置いて、空腹からの BLEEDING 発症などの
            # 連鎖を同 tick 内で処理しやすくする。HP 0 で DEAD outcome
            # 連鎖は E-3a の handler に任せる (publisher 経由)。
            self._run_stage("status_effects", self._status_effects_stage, current_tick)
        if self._monster_spawn_stage is not None:
            # 動的 spawn / despawn 判定。day_night / weather / flag を
            # 評価し、条件付きスロットを必要に応じてスポーン or デスポーン。
            # behavior の前に走らせることで「その tick で spawn したモンスター
            # が同 tick の behavior に乗る」。
            self._run_stage("monster_spawn", self._monster_spawn_stage, current_tick)
        if self._monster_behavior_stage is not None:
            # モンスター行動 tick: attack / wander / pack 行動。
            # needs_decay 後に置くことで「同 tick でモンスターが空腹を
            # 感じてから行動を決める」順序になる (将来の forage 連動)。
            self._run_stage("monster_behavior", self._monster_behavior_stage, current_tick)
        if self._food_spoilage_stage is not None:
            # Phase D-2: 食料腐敗判定。pure な item state mutation で
            # tick 内の他 stage と依存しないが、観測 callback を持つ可能性
            # を考えて post_tick_hooks の前に commit に乗せる。
            # 順序は他 stage 後で OK: 同 tick で gather → spoilage 判定 されても
            # acquired_at_tick が今回 tick で初期化されるだけで、閾値到達は
            # 次回以降。
            self._run_stage("food_spoilage", self._food_spoilage_stage, current_tick)
        if self._trade_offer_expiry_stage is not None:
            # 返事のないまま期限を過ぎた取引を片付ける。**その tick の
            # 世界変化がすべて終わった後**に判定する: エージェントの手番は
            # post_tick_hooks で走るので、同 tick に承諾された提案は既に
            # store から消えており、消えたものを期限切れにする誤りが
            # 起きない。
            self._run_stage("trade_offer_expiry", self._trade_offer_expiry_stage, current_tick)
        if self._market_order_expiry_stage is not None:
            # 板の注文も同じ理由で、その tick の変化が終わった後に片付ける。
            # 提案の片付けと並べておくのは、**期限は 1 か所にまとまって
            # いる方が、次に足す人が忘れにくい**ため。
            self._run_stage("market_order_expiry", self._market_order_expiry_stage, current_tick)
        if self._player_outcome_rule_stage is not None:
            # 当 tick の移動を反映したあとに判定し、「移動で summit に着いた
            # tick に、手番より前に救助される」を保つ。手番の中で立った
            # フラグは、手番のあとの判定 (_run_post_tick_hooks) で拾う。
            self._run_stage("player_outcome_rule", self._player_outcome_rule_stage, current_tick)
        if self._death_grace_stage is not None:
            # Issue #621: ダウン後 30 tick 経過した player を DEAD 確定。
            # player_outcome_rule_stage の **後** に置くことで、同 tick で
            # RESCUED 確定した player に対する DEAD 上書きを set_outcome
            # の冪等で防ぐ (= 順序が逆だと DEAD → RESCUED 試行で no-op)。
            self._run_stage("death_grace", self._death_grace_stage, current_tick)
        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_stage(self, name: str, stage: _SpotGraphTickStage, current_tick: WorldTick) -> None:
        # 段の中で 1 体ずつ包んでいない例外の受け皿。取りやめる単位は段そのもの。
        with self._failure_isolator.unit(stage=name, tick=current_tick, target_kind="stage"):
            stage.run(current_tick)

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        failures: list[tuple[str, Exception]] = []
        # 順序が重要:
        #   graph_event_flusher → heartbeat → llm_turn_trigger → player_outcome_rule。
        # PR-N: graph_event_flusher を heartbeat より先に走らせる。tick stage
        # (= monster_behavior / status_effects / needs_decay) で graph に
        # 積まれた events を flush して観測 pipeline に流すと、その観測の
        # schedules_turn=True が heartbeat より先に turn を積む → turn_trigger
        # が拾える。逆順だと heartbeat 後の turn 実行までに events が
        # 観測 buffer に届かない silent failure になる。
        # player_outcome_rule を手番のあとにもう一度走らせ、手番の中で立った
        # フラグを、その tick のうちに、そのときの位置で判定する。次の tick に
        # 回すと、次の tick の移動が先に反映され、籠が上がったあとに乗り場へ
        # 着いた人まで脱出になる (design_decisions D1618)。
        hooks: tuple[tuple[str, Any, Callable[[Any], None]], ...] = (
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
            (
                "player_outcome_rule",
                self._player_outcome_rule_stage,
                lambda stage: stage.run_after_turns(current_tick),
            ),
        )
        for hook_name, hook, runner in hooks:
            if hook is None:
                continue
            try:
                with self._failure_isolator.unit(
                    stage=f"post_tick.{hook_name}",
                    tick=current_tick,
                    target_kind="post_tick_hook",
                    command_scoped=False,
                ):
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

    def _execute_with_error_handling(self, operation: Callable[[], WorldTick], context: dict[str, Any]) -> WorldTick:
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
                f"{context.get('action', 'spot_graph_tick')} failed: {exc!s}",
                original_exception=exc,
            ) from exc


__all__ = ["SpotGraphSimulationApplicationService"]


class _SpotGraphTickStage(Protocol):
    def run(self, current_tick: WorldTick) -> None: ...


class _PlayerOutcomeRuleTickStage(_SpotGraphTickStage, Protocol):
    def run_after_turns(self, current_tick: WorldTick) -> None: ...

"""tick経過で欲求を自然増加させるステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で全プレイヤーの空腹・疲労を緩やかに増加させる。

Phase v2-hunger: HUNGER が max (= 限界) に達したプレイヤーには、毎 tick
HP を漸減させる Minecraft 風の飢餓ダメージも適用する。HP 0 になった場合
は PlayerStatusAggregate が PlayerDownedEvent を積み、本番ではCommandScopeの
確定後配送を経て PlayerDownedOutcomeHandler へ届く (E-3a 経路)。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.needs_decay_tick import (
    DEFAULT_NEED_RATES,
    NeedsDecayTick,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandScopeFactoryPort
    from ai_rpg_world.application.world_graph.player_status_tick_command_repository_provider import (
        PlayerStatusTickCommandRepositoryProviderPort,
    )

_logger = logging.getLogger(__name__)


class SpotGraphNeedsDecayStageService:
    """毎tick で全プレイヤーの欲求を自然増加させる。

    ``_SpotGraphTickStage`` Protocol に準拠。
    ``SpotGraphSimulationApplicationService`` の tick パイプラインに
    ``needs_decay_stage`` として注入する。

    Args:
        player_status_repository: PlayerStatusAggregate を引く repo。
        rates: 各 NeedType の増加 rate (tick あたり)。default は HUNGER + FATIGUE
            ともに +1/tick。0 にすると該当 need は増加しない。
        starvation_damage_per_tick: HUNGER が limit に達したプレイヤーに
            毎 tick 適用する HP ダメージ。default 0 (= 無効、後方互換)。
            v2 survival_island のような飢餓メカニクスが要るシナリオは
            正の値 (例: 1) を指定する。0 にしておけば既存シナリオ
            (脱出ゲーム等) の挙動は完全に不変。
        event_publisher: HP 0 で発生する PlayerDownedEvent を流すための
            直接構築用publisher。本番のCommandScope経路では使わず、
            repository providerがeventsを収集して確定後に配送する。
        state_collapse_evidence_transcriber: PR-D。hunger max 到達を高
            salience の ``BeliefEvidence`` に転記する transcriber
            (``StateCollapseEvidenceTranscriber``)。None なら完全 no-op
            (= STATE_COLLAPSE_EVIDENCE_ENABLED OFF 相当、導入前と挙動不変)。
        state_collapse_being_id_resolver: player_id から being_id を解決する
            callable。transcriber と対で必要 (どちらか None なら no-op)。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        *,
        rates: Dict[NeedType, int] | None = None,
        starvation_damage_per_tick: int = 0,
        fatigue_critical_damage_per_tick: int = 0,
        fatigue_critical_threshold: int = 95,
        event_publisher: Optional[Any] = None,
        state_collapse_evidence_transcriber: Optional[Any] = None,
        state_collapse_being_id_resolver: Optional[
            Callable[[PlayerId], Optional[Any]]
        ] = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._rates = rates or dict(DEFAULT_NEED_RATES)
        self._starvation_damage_per_tick = max(0, starvation_damage_per_tick)
        # PR β: 疲労が threshold (default 95) を超えたプレイヤーに毎 tick
        # 微小 HP ダメージを与える。「限界まで疲弊すると徐々に体が壊れる」を
        # 表現するための飢餓と同型のメカニクス。default 0 (= 無効、後方互換)。
        self._fatigue_critical_damage_per_tick = max(0, fatigue_critical_damage_per_tick)
        self._fatigue_critical_threshold = fatigue_critical_threshold
        self._event_publisher = event_publisher
        self._state_collapse_evidence_transcriber = state_collapse_evidence_transcriber
        self._state_collapse_being_id_resolver = state_collapse_being_id_resolver
        self._command_scope_factory = command_scope_factory

    def set_event_publisher(self, publisher: Optional[Any]) -> None:
        """publisher を後付け注入する (runtime 順序依存の解消用)。

        weather / food_spoilage と同じ pattern。constructor は publisher 無しで
        作っておき、runtime 構築完了後に bind する。
        """
        self._event_publisher = publisher

    def set_state_collapse_evidence_wiring(
        self,
        transcriber: Optional[Any],
        being_id_resolver: Optional[Callable[[PlayerId], Optional[Any]]],
    ) -> None:
        """PR-D: transcriber / being_id_resolver を後付け注入する。

        ``set_event_publisher`` と同じ pattern (runtime 構築完了後に bind)。
        """
        self._state_collapse_evidence_transcriber = transcriber
        self._state_collapse_being_id_resolver = being_id_resolver

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageをplayer status単位の独立した確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        """全プレイヤーの欲求を増加させ、一括保存する + 飢餓ダメージを適用。"""
        if self._command_scope_factory is not None:
            evidence_statuses: list[Any] = []
            try:
                with self._command_scope_factory.create() as scope:
                    repositories = scope.repositories
                    if repositories is None:
                        raise RuntimeError(
                            "needs decay tick用repository providerがありません"
                        )
                    evidence_statuses, _legacy_events = self._run_with_repository(
                        repositories.player_statuses,
                        publish_legacy_events=False,
                    )
            except CommandPostCommitException:
                # statusは確定済みなので、evidenceも確定状態に追随させてから
                # commit後処理の失敗を呼出し側へ返す。
                self._sync_hunger_max_evidence_all(evidence_statuses)
                raise
            self._sync_hunger_max_evidence_all(evidence_statuses)
            return
        evidence_statuses, legacy_events = self._run_with_repository(
            self._player_status_repository,
            publish_legacy_events=True,
        )
        self._sync_hunger_max_evidence_all(evidence_statuses)
        if legacy_events and self._event_publisher is not None:
            self._event_publisher.publish_all(legacy_events)

    def _run_with_repository(
        self,
        player_status_repository: PlayerStatusRepository,
        *,
        publish_legacy_events: bool,
    ) -> tuple[list[Any], list[Any]]:
        """指定repository上でneedsを進め、evidence対象と旧eventを返す。"""
        updated = []
        starvation_events: list = []
        evidence_statuses: list[Any] = []
        for status in player_status_repository.find_all():
            if not status.can_act():
                continue
            if len(status.needs) == 0:
                continue
            result = status.apply_needs_decay_tick(
                NeedsDecayTick(
                    rates=self._rates,
                    starvation_damage_per_tick=self._starvation_damage_per_tick,
                    fatigue_critical_damage_per_tick=self._fatigue_critical_damage_per_tick,
                    fatigue_critical_threshold=self._fatigue_critical_threshold,
                )
            )
            evidence_statuses.append(status)
            if result.changed:
                updated.append(status)
                if publish_legacy_events and self._event_publisher is not None:
                    starvation_events.extend(status.get_events())
                    status.clear_events()
        if updated:
            player_status_repository.save_all(updated)
        return evidence_statuses, starvation_events

    def _sync_hunger_max_evidence_all(self, statuses: list[Any]) -> None:
        """確定済みstatusだけをevidenceへ転記する。"""
        for status in statuses:
            self._sync_hunger_max_evidence(status)

    def _sync_hunger_max_evidence(self, status: Any) -> None:
        """PR-D: hunger.value と max_value を比較し、transcriber の dedup 状態を
        同期する。

        - max 到達中 (>=): ``record_hunger_max_evidence`` (transcriber 側で
          既に記録済みなら二重には積まれない)
        - max 未満: ``clear_hunger_max_state`` (食事等で回復した場合に次回
          再到達したとき新しい evidence を積めるようにする)

        transcriber / being_id_resolver のどちらかが未配線、または
        being_id が解決できないときは完全に no-op。evidence 記録は
        best-effort な副作用なので、transcriber 側の例外はここで握って
        tick 処理全体を止めない。
        """
        transcriber = self._state_collapse_evidence_transcriber
        resolver = self._state_collapse_being_id_resolver
        if transcriber is None or resolver is None:
            return
        hunger = status.needs.get(NeedType.HUNGER)
        if hunger is None:
            return
        try:
            being_id = resolver(status.player_id)
        except Exception:
            _logger.exception(
                "state_collapse_being_id_resolver failed for player_id=%s",
                status.player_id,
            )
            return
        if being_id is None:
            return
        try:
            if hunger.value >= hunger.max_value:
                transcriber.record_hunger_max_evidence(being_id)
            else:
                transcriber.clear_hunger_max_state(being_id)
        except Exception:
            _logger.exception(
                "state_collapse_evidence_transcriber failed for being_id=%s",
                being_id,
            )

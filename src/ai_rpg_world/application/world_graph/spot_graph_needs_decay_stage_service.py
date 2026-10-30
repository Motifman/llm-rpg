"""tick経過で欲求を自然増加させるステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で全プレイヤーの空腹・疲労を緩やかに増加させる。

Phase v2-hunger: HUNGER が max (= 限界) に達したプレイヤーには、毎 tick
HP を漸減させる Minecraft 風の飢餓ダメージも適用する。HP 0 になった場合
は PlayerStatusAggregate が PlayerDownedEvent を積み、本番ではCommandScopeの
commit前必須処理で身体・死亡猶予まで一緒に確定した後、観測だけを確定後配送する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.needs_decay_tick import (
    DEFAULT_NEED_RATES,
    NeedsDecayTick,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactoryPort
    from ai_rpg_world.application.world_graph.player_status_tick_command_repository_provider import (
        PlayerStatusTickCommandRepositoryProviderPort,
    )


class SpotGraphNeedsDecayStageService:
    """毎tick で全プレイヤーの欲求を自然増加させる。

    ``_SpotGraphTickStage`` Protocol に準拠。
    ``SpotGraphSimulationApplicationService`` の tick パイプラインに
    ``needs_decay_stage`` として注入する。

    Args:
        rates: 各 NeedType の増加 rate (tick あたり)。default は HUNGER + FATIGUE
            ともに +1/tick。0 にすると該当 need は増加しない。
        starvation_damage_per_tick: HUNGER が limit に達したプレイヤーに
            毎 tick 適用する HP ダメージ。default 0 (= 無効、後方互換)。
            v2 survival_island のような飢餓メカニクスが要るシナリオは
            正の値 (例: 1) を指定する。0 にしておけば既存シナリオ
            (脱出ゲーム等) の挙動は完全に不変。
    """

    def __init__(
        self,
        *,
        rates: dict[NeedType, int] | None = None,
        starvation_damage_per_tick: int = 0,
        fatigue_critical_damage_per_tick: int = 0,
        fatigue_critical_threshold: int = 95,
        command_scope_factory: CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort] | None = None,
    ) -> None:
        self._rates = rates or dict(DEFAULT_NEED_RATES)
        self._starvation_damage_per_tick = max(0, starvation_damage_per_tick)
        # PR β: 疲労が threshold (default 95) を超えたプレイヤーに毎 tick
        # 微小 HP ダメージを与える。「限界まで疲弊すると徐々に体が壊れる」を
        # 表現するための飢餓と同型のメカニクス。default 0 (= 無効、後方互換)。
        self._fatigue_critical_damage_per_tick = max(0, fatigue_critical_damage_per_tick)
        self._fatigue_critical_threshold = fatigue_critical_threshold
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort],
    ) -> None:
        """本番stageをplayer status単位の独立した確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        """全プレイヤーの欲求を増加させ、一括保存する + 飢餓ダメージを適用。"""
        scope_factory = self._command_scope_factory
        if scope_factory is None:
            raise RuntimeError("needs decay tickにはCommandScopeFactoryの配線が必要です")
        with scope_factory.create() as scope:
            repositories = scope.repositories
            if repositories is None:
                raise RuntimeError("needs decay tick用repository providerがありません")
            self._run_with_repository(repositories.player_statuses)

    def _run_with_repository(
        self,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        """指定repository上でneedsを進める。"""
        updated = []
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
            if result.changed:
                updated.append(status)
        if updated:
            player_status_repository.save_all(updated)

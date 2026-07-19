"""``SpotGraphSimulationApplicationService.tick()`` 経由での
``PlayerDeathGraceTickStage`` 実経路統合テスト (PR-K)。

実 run r1_001 (survival_island_v3_coop) で発生したクラッシュの再発防止テスト。
単体テストで ``PlayerDeathGraceTickStage.run()`` に int を渡して green に
なっていても、実際の tick 経路では ``GameTimeProvider.advance_tick()`` が
返す ``WorldTick`` がそのまま渡るため、そこでしか踏めない型不一致が起こり
得る (#710 のバグもこの経路で初めて露見した)。このテストは
``InMemoryGameTimeProvider`` + ``SpotGraphSimulationApplicationService`` を
組み立て、``tick()`` を直接呼ぶことで実経路の型を保証する。
"""

from __future__ import annotations

from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
    PlayerDeathGraceTickStage,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)

GRACE_TICKS = 30


class TestDeathGraceStageThroughSimulationServiceTick:
    """``simulation_service.tick()`` が渡す実際の ``WorldTick`` で完結させる。"""

    def _build(
        self, outcome_registry: PlayerOutcomeRegistry, grace_timer: PlayerDeathGraceTimer
    ) -> SpotGraphSimulationApplicationService:
        death_grace_stage = PlayerDeathGraceTickStage(
            outcome_registry=outcome_registry,
            grace_timer=grace_timer,
            grace_ticks=GRACE_TICKS,
        )
        return SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            unit_of_work=InMemoryUnitOfWork(),
            death_grace_stage=death_grace_stage,
        )

    def test_down_after_tick_does_not_crash(self) -> None:
        """r1_001 で SystemErrorException になった状況の再現。

        down 登録直後の 1 tick で ``TypeError`` が飛ばずに tick が完了する
        こと自体が最重要の確認事項 (修正前はここで tick 全体が停止した)。
        """
        outcome_registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        grace_timer = PlayerDeathGraceTimer()
        service = self._build(outcome_registry, grace_timer)

        # PlayerDownedOutcomeHandler が行う登録を模す (down が起きた tick=1)。
        service.tick()  # tick=1
        grace_timer.register(PlayerId(1), downed_at_tick=1)

        # 例外なく次 tick に進めること (= 実験全体が死なない)。
        service.tick()  # tick=2

        assert outcome_registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_grace_ticks_after_dead(self) -> None:
        """down → grace_ticks 経過 → overdue 検出 → DEAD 確定、を tick() 越しに。"""
        outcome_registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        grace_timer = PlayerDeathGraceTimer()
        service = self._build(outcome_registry, grace_timer)

        service.tick()  # tick=1
        grace_timer.register(PlayerId(1), downed_at_tick=1)

        # tick=1 から grace_ticks(30) 経過する tick=31 まで進める。
        for _ in range(GRACE_TICKS):
            service.tick()

        assert outcome_registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD
        assert grace_timer.is_pending(PlayerId(1)) is False

    def test_revive_grace_after_dead(self) -> None:
        """down → revive (cancel) → grace_ticks 経過、でも DEAD にならない。"""
        outcome_registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        grace_timer = PlayerDeathGraceTimer()
        service = self._build(outcome_registry, grace_timer)

        service.tick()  # tick=1
        grace_timer.register(PlayerId(1), downed_at_tick=1)

        service.tick()  # tick=2
        # PlayerRevivedOutcomeHandler が行う cancel を模す。
        grace_timer.cancel(PlayerId(1))

        for _ in range(GRACE_TICKS):
            service.tick()

        assert outcome_registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_down_after_multiple_tick(self) -> None:
        """down 発生が実験全体を止めないことの確認 (修正後は自然に満たされる)。"""
        outcome_registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        grace_timer = PlayerDeathGraceTimer()
        service = self._build(outcome_registry, grace_timer)

        for tick_no in range(1, 6):
            result_tick = service.tick()
            if tick_no == 2:
                grace_timer.register(PlayerId(1), downed_at_tick=tick_no)
            assert result_tick.value == tick_no

        # 5 tick 進めても grace_ticks(30) 未経過なので player 1 はまだ確定しない。
        assert outcome_registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED
        assert outcome_registry.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.UNRESOLVED

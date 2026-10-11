"""手番のあとの個人結果規則の判定が、死亡の猶予の段との順番の約束を崩さないことを保証する (#1618)。

世界の段の中では「個人結果規則 → 死亡の猶予」の順で、同じ tick の救助を死亡で
上書きしない。手番のあとにもう一度判定を走らせても、手番で決まった救助は次の
tick の猶予の段で上書きされない。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)

_PLAYER = PlayerId(1)


@dataclass
class _World:
    flags: set[str]


@dataclass
class _RescueWhenFlagSet:
    """フラグが立っていれば RESCUED にする、個人結果規則の段の代わり。"""

    world: _World
    registry: PlayerOutcomeRegistry

    def run(self, current_tick: WorldTick) -> None:
        if "lift_departed" in self.world.flags:
            self.registry.set_outcome(_PLAYER, PlayerOutcomeEnum.RESCUED)

    def run_after_turns(self, current_tick: WorldTick) -> None:
        self.run(current_tick)


@dataclass
class _DeadFromTick:
    """指定 tick 以降に DEAD にする、死亡の猶予の段の代わり。"""

    registry: PlayerOutcomeRegistry
    expires_at: int

    def run(self, current_tick: WorldTick) -> None:
        if current_tick.value >= self.expires_at:
            self.registry.set_outcome(_PLAYER, PlayerOutcomeEnum.DEAD)


@dataclass
class _DepartInTurnAt:
    """指定 tick の手番でフラグを立てる llm_turn_trigger の代わり。"""

    world: _World
    time_provider: InMemoryGameTimeProvider
    departs_at: int

    def schedule_turn(self, player_id: PlayerId) -> None:
        pass

    def run_scheduled_turns(self) -> None:
        if self.time_provider.get_current_tick().value == self.departs_at:
            self.world.flags.add("lift_departed")


def _service(*, departs_at: int, grace_expires_at: int) -> tuple[
    SpotGraphSimulationApplicationService, PlayerOutcomeRegistry
]:
    world = _World(flags=set())
    registry = PlayerOutcomeRegistry.new_for_players([_PLAYER])
    time_provider = InMemoryGameTimeProvider()
    service = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        player_outcome_rule_stage=_RescueWhenFlagSet(world, registry),
        death_grace_stage=_DeadFromTick(registry, grace_expires_at),
        llm_turn_trigger=_DepartInTurnAt(world, time_provider, departs_at),
    )
    return service, registry


class TestPlayerOutcomeRuleAfterTurnsAndDeathGrace:
    """手番で決まった救助と死亡の猶予の切れ目が隣り合うときの結果を保証する。"""

    def test_rescue_decided_after_turns_is_not_overwritten_by_next_tick_grace(self) -> None:
        """tick 1 の手番で昇降機が出て RESCUED になった人は、tick 2 で猶予が切れても RESCUED のまま。"""
        service, registry = _service(departs_at=1, grace_expires_at=2)

        service.tick()
        rescued_in_departure_tick = registry.get_outcome(_PLAYER)
        service.tick()

        assert rescued_in_departure_tick is PlayerOutcomeEnum.RESCUED
        assert registry.get_outcome(_PLAYER) is PlayerOutcomeEnum.RESCUED

    def test_grace_expiring_before_the_turn_departure_stays_dead(self) -> None:
        """猶予が切れた tick 1 の世界の段で DEAD になった人は、同じ tick の手番で昇降機が出ても RESCUED にならない。"""
        service, registry = _service(departs_at=1, grace_expires_at=1)

        service.tick()

        assert registry.get_outcome(_PLAYER) is PlayerOutcomeEnum.DEAD

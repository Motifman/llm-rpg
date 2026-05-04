"""SpotGraphNeedsDecayStageService のユニットテスト。

tick経過で欲求が自然増加する仕組みを検証する。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _make_player(pid: int = 1, needs: AgentNeeds | None = None) -> PlayerStatusAggregate:
    exp_table = ExpTable(base_exp=100.0, exponent=1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(pid),
        base_stats=BaseStats(max_hp=100, max_mp=50, attack=10, defense=10, speed=10, critical_rate=0.05, evasion_rate=0.05),
        stat_growth_factor=StatGrowthFactor(hp_factor=1.0, mp_factor=1.0, attack_factor=1.0, defense_factor=1.0, speed_factor=1.0, critical_rate_factor=0.0, evasion_rate_factor=0.0),
        exp_table=exp_table,
        growth=Growth(level=1, total_exp=0, exp_table=exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        needs=needs,
    )


class TestNeedsDecayStageService:
    """tick経過で欲求が増加するサービスのテスト"""

    def test_hunger_increases_per_tick(self) -> None:
        """1tick で空腹が増加すること"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player()
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 2, NeedType.FATIGUE: 1})
        svc.run(WorldTick(1))

        updated = repo.find_by_id(PlayerId(1))
        assert updated is not None
        hunger = updated.needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 2

    def test_fatigue_increases_per_tick(self) -> None:
        """1tick で疲労が増加すること"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player()
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 1, NeedType.FATIGUE: 3})
        svc.run(WorldTick(1))

        updated = repo.find_by_id(PlayerId(1))
        assert updated is not None
        fatigue = updated.needs.get(NeedType.FATIGUE)
        assert fatigue is not None
        assert fatigue.value == 3

    def test_multiple_ticks_accumulate(self) -> None:
        """複数tick で欲求が蓄積すること"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player()
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 5, NeedType.FATIGUE: 3})
        for tick in range(1, 11):
            svc.run(WorldTick(tick))

        updated = repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.needs.get(NeedType.HUNGER).value == 50  # type: ignore
        assert updated.needs.get(NeedType.FATIGUE).value == 30  # type: ignore

    def test_need_clamps_at_max(self) -> None:
        """欲求が最大値を超えないこと"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player()
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 50, NeedType.FATIGUE: 0})
        svc.run(WorldTick(1))
        svc.run(WorldTick(2))
        svc.run(WorldTick(3))  # 50 + 50 + 50 = 150 → clamp to 100

        updated = repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.needs.get(NeedType.HUNGER).value == 100  # type: ignore

    def test_empty_needs_skipped(self) -> None:
        """欲求が空のプレイヤーはスキップされること"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player(needs=AgentNeeds.empty())
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo)
        svc.run(WorldTick(1))  # エラーなく完了すること

    def test_multiple_players(self) -> None:
        """複数プレイヤーがそれぞれ独立に更新されること"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        repo.save(_make_player(pid=1))
        repo.save(_make_player(pid=2))

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 5, NeedType.FATIGUE: 2})
        svc.run(WorldTick(1))

        p1 = repo.find_by_id(PlayerId(1))
        p2 = repo.find_by_id(PlayerId(2))
        assert p1 is not None and p2 is not None
        assert p1.needs.get(NeedType.HUNGER).value == 5  # type: ignore
        assert p2.needs.get(NeedType.HUNGER).value == 5  # type: ignore

    def test_downed_player_skipped(self) -> None:
        """ダウン状態のプレイヤーは欲求が増加しないこと"""
        data_store = InMemoryDataStore()
        repo = InMemoryPlayerStatusRepository(data_store)
        player = _make_player()
        player.apply_damage(999)  # HP 0 → is_down = True
        repo.save(player)

        svc = SpotGraphNeedsDecayStageService(repo, rates={NeedType.HUNGER: 10, NeedType.FATIGUE: 10})
        svc.run(WorldTick(1))

        updated = repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.needs.get(NeedType.HUNGER).value == 0  # type: ignore
        assert updated.needs.get(NeedType.FATIGUE).value == 0  # type: ignore

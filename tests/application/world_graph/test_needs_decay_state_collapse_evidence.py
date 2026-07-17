"""PR-D: SpotGraphNeedsDecayStageService から hunger max 到達を
StateCollapseEvidenceTranscriber へ転記する配線を検証する。

判定基準 (hunger.value >= hunger.max_value) 自体は既存の starvation ダメージ
判定と同じ値を見るが、evidence 転記は starvation_damage_per_tick の設定に
依存しない (「空腹が限界に達した」という事実そのものが対象であり、飢餓
ダメージの有無とは独立)。transcriber / being_id_resolver が未配線
(= フラグ OFF 相当) のときは完全に no-op で、既存の needs decay 挙動は
変わらない。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _build_status_with_hunger(hunger_value: int, hp: int = 100) -> PlayerStatusAggregate:
    from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
    from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
    from ai_rpg_world.domain.player.value_object.gold import Gold
    from ai_rpg_world.domain.player.value_object.growth import Growth
    from ai_rpg_world.domain.player.value_object.hp import Hp
    from ai_rpg_world.domain.player.value_object.mp import Mp
    from ai_rpg_world.domain.player.value_object.stamina import Stamina
    from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
    exp_table = ExpTable(100, 1.5)
    status = PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )
    if hunger_value > 0:
        status.increase_need(NeedType.HUNGER, hunger_value)
    return status


class _TranscriberSpy:
    def __init__(self) -> None:
        self.recorded: list[BeingId] = []
        self.cleared: list[BeingId] = []

    def record_hunger_max_evidence(self, being_id: BeingId):
        self.recorded.append(being_id)
        return None

    def clear_hunger_max_state(self, being_id: BeingId) -> None:
        self.cleared.append(being_id)


class _RaisingTranscriber:
    def record_hunger_max_evidence(self, being_id: BeingId):
        raise RuntimeError("boom")

    def clear_hunger_max_state(self, being_id: BeingId) -> None:
        raise RuntimeError("boom")


class TestNoWiringIsNoOp:
    def test_transcriber未設定なら例外なく完了し呼ばれない相当(self) -> None:
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo)

        stage.run(WorldTick(1))  # 例外なく完了

        assert status.needs.get(NeedType.HUNGER).value == 100


class TestHungerMaxEvidenceWiring:
    def test_hunger_maxに到達すると_record_hunger_max_evidenceを呼ぶ(self) -> None:
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        transcriber = _TranscriberSpy()
        being_id = BeingId("being-1")
        stage = SpotGraphNeedsDecayStageService(
            repo,
            state_collapse_evidence_transcriber=transcriber,
            state_collapse_being_id_resolver=lambda pid: being_id,
        )

        stage.run(WorldTick(1))  # HUNGER 99 → 100 (max)

        assert transcriber.recorded == [being_id]

    def test_hunger_max未満なら_clear_hunger_max_stateを呼ぶ(self) -> None:
        status = _build_status_with_hunger(hunger_value=10, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        transcriber = _TranscriberSpy()
        being_id = BeingId("being-1")
        stage = SpotGraphNeedsDecayStageService(
            repo,
            state_collapse_evidence_transcriber=transcriber,
            state_collapse_being_id_resolver=lambda pid: being_id,
        )

        stage.run(WorldTick(1))  # HUNGER 10 → 11 (max 未満)

        assert transcriber.recorded == []
        assert transcriber.cleared == [being_id]

    def test_being_id解決失敗なら_transcriberを呼ばない(self) -> None:
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        transcriber = _TranscriberSpy()
        stage = SpotGraphNeedsDecayStageService(
            repo,
            state_collapse_evidence_transcriber=transcriber,
            state_collapse_being_id_resolver=lambda pid: None,
        )

        stage.run(WorldTick(1))

        assert transcriber.recorded == []
        assert transcriber.cleared == []

    def test_transcriberが例外を投げても_tick処理は止まらない(self) -> None:
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        being_id = BeingId("being-1")
        stage = SpotGraphNeedsDecayStageService(
            repo,
            state_collapse_evidence_transcriber=_RaisingTranscriber(),
            state_collapse_being_id_resolver=lambda pid: being_id,
        )

        stage.run(WorldTick(1))  # 例外なく完了

        assert status.needs.get(NeedType.HUNGER).value == 100


class TestSetterInjection:
    def test_set_state_collapse_evidence_wiringで後付けできる(self) -> None:
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo)
        transcriber = _TranscriberSpy()
        being_id = BeingId("being-1")

        stage.set_state_collapse_evidence_wiring(transcriber, lambda pid: being_id)
        stage.run(WorldTick(1))

        assert transcriber.recorded == [being_id]

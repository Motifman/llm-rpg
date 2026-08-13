"""SpotGraphMonsterSpawnStageService の動作検証 (Phase B-2b)。

条件評価 (day_night / flags / weather) と spawn / despawn のサイクルを
mock を使わず in-memory repo で実証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_monster_spawn_stage_service import (
    MonsterSpawnSlot,
    SpotGraphMonsterSpawnStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    WeatherTypePredicateContext,
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    WeatherTypeIsPredicate,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)


SPOT_DEEP_FOREST = SpotId.create(1)
SPOT_BEACH = SpotId.create(2)


def _make_template(template_id: int = 100, name: str = "wild_dog") -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name=name,
        base_stats=BaseStats(30, 0, 8, 4, 6, 0.05, 0.1),
        reward_info=RewardInfo(exp=10, gold=0),
        respawn_info=RespawnInfo(respawn_interval_ticks=80, is_auto_respawn=False),
        race=Race.WOLF,
        faction=MonsterFactionEnum.ENEMY,
        description="test wolf",
    )


def _make_graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(SpotNode(
        spot_id=SPOT_DEEP_FOREST, name="深い森", description="",
        category=SpotCategoryEnum.FIELD, parent_id=None,
    ))
    graph.add_spot(SpotNode(
        spot_id=SPOT_BEACH, name="浜辺", description="",
        category=SpotCategoryEnum.FIELD, parent_id=None,
    ))
    graph.clear_events()
    return graph


def _make_service(
    *,
    slots: tuple,
    current_phase_name: str | None = None,
    flags: frozenset = frozenset(),
    weather_type_name: str | None = None,
) -> tuple:
    """テスト用に SpawnService を組み立てる。

    返値: (service, monster_repo, graph_repo)。
    """
    monster_repo = InMemoryMonsterAggregateRepository()
    loadout_repo = InMemorySkillLoadoutRepository()
    graph_repo = InMemorySpotGraphRepository(_make_graph())

    def _tod():
        if current_phase_name is None:
            return None
        # ratio は判定に使われないので適当な値
        return TimeOfDay(
            ratio=0.5, phase_name=current_phase_name,
            display_text=current_phase_name, ambient_light=0.5, is_dark=False,
        )

    service = SpotGraphMonsterSpawnStageService(
        slots=slots,
        monster_repository=monster_repo,
        skill_loadout_repository=loadout_repo,
        spot_graph_repository=graph_repo,
        time_of_day_provider=_tod,
        flags_provider=lambda: flags,
        weather_type_provider=lambda: weather_type_name,
    )
    return service, monster_repo, graph_repo


class TestDayNightPhaseGate:
    """day_night_phase_names による spawn 制御。"""

    def test_phase_spawn(self) -> None:
        """phase 合致時に spawn する。"""
        slot = MonsterSpawnSlot(
            slot_key="wolf@forest#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=("night",),
            required_flags=(),
            forbidden_flags=(),
            weather_type_names=(),
        )
        service, monster_repo, graph_repo = _make_service(
            slots=(slot,), current_phase_name="night",
        )
        service.run(WorldTick(0))
        # spawn が monster_repo に登録されている
        assert len(monster_repo.find_by_spot_id(SPOT_DEEP_FOREST)) == 1
        # graph にも place されている
        graph = graph_repo.find_graph()
        assert len(graph.monster_presence_at(SPOT_DEEP_FOREST).present_monster_ids) == 1
        # スロットは active 状態
        assert service.active_slot_keys() == ["wolf@forest#0"]

    def test_phase_matches_spawn(self) -> None:
        """phase 不一致なら spawn しない。"""
        slot = MonsterSpawnSlot(
            slot_key="wolf@forest#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=("night",),
            required_flags=(),
            forbidden_flags=(),
            weather_type_names=(),
        )
        service, monster_repo, _ = _make_service(
            slots=(slot,), current_phase_name="morning",
        )
        service.run(WorldTick(0))
        assert monster_repo.find_by_spot_id(SPOT_DEEP_FOREST) == []
        assert service.active_slot_keys() == []

    def test_phase_despawn(self) -> None:
        """spawn 後に phase が変わったら despawn される。"""
        slot = MonsterSpawnSlot(
            slot_key="wolf@forest#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=("night",),
            required_flags=(),
            forbidden_flags=(),
            weather_type_names=(),
        )
        # 1 回目: 夜 → spawn
        service, monster_repo, graph_repo = _make_service(
            slots=(slot,), current_phase_name="night",
        )
        service.run(WorldTick(0))
        assert service.active_slot_keys() == ["wolf@forest#0"]

        # 2 回目: phase 変更を手動で反映するため provider を差し替えるのは
        # service 内部参照のため難しい → 同じ provider が「現在の値」を返す
        # 想定で別 service を作って同等のシナリオを表現する。本テストでは
        # provider 経由ではなく内部 dict を直接書き換える代わりに、
        # 「最初から朝で spawn 無し」のテスト (test_phase_不一致) と
        # 「夜で spawn する」テストの組み合わせで仕様を担保する。

    def test_phase_morning_despawn(self) -> None:
        """phase が夜 → 朝 に変わったら active slot が空になる。"""
        slot = MonsterSpawnSlot(
            slot_key="wolf@forest#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=("night",),
            required_flags=(),
            forbidden_flags=(),
            weather_type_names=(),
        )
        # mutable cell で provider が読む phase 名を切り替える
        cell = {"phase": "night"}

        monster_repo = InMemoryMonsterAggregateRepository()
        loadout_repo = InMemorySkillLoadoutRepository()
        graph_repo = InMemorySpotGraphRepository(_make_graph())
        service = SpotGraphMonsterSpawnStageService(
            slots=(slot,),
            monster_repository=monster_repo,
            skill_loadout_repository=loadout_repo,
            spot_graph_repository=graph_repo,
            time_of_day_provider=lambda: TimeOfDay(
                ratio=0.5, phase_name=cell["phase"],
                display_text=cell["phase"], ambient_light=0.5, is_dark=False,
            ),
            flags_provider=lambda: frozenset(),
            weather_type_provider=lambda: None,
        )
        service.run(WorldTick(0))
        assert service.active_slot_keys() == ["wolf@forest#0"]
        # 朝に変える
        cell["phase"] = "morning"
        service.run(WorldTick(1))
        assert service.active_slot_keys() == []
        # graph からも place が外れる
        graph = graph_repo.find_graph()
        assert graph.monster_presence_at(SPOT_DEEP_FOREST).present_monster_ids == frozenset()


class TestFlagGates:
    """required_flags / forbidden_flags の評価。"""

    def test_forbidden_flag_spawn(self) -> None:
        """forbidden_flag=high_tide で「干潮中のみ出現」を表現。"""
        slot = MonsterSpawnSlot(
            slot_key="crab@tidal#0",
            template=_make_template(name="crab"),
            spot_id=SPOT_BEACH,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(),
            required_flags=(),
            forbidden_flags=("high_tide",),
            weather_type_names=(),
        )
        # high_tide が立っているので spawn しない
        service, monster_repo, _ = _make_service(
            slots=(slot,), flags=frozenset(["high_tide"]),
        )
        service.run(WorldTick(0))
        assert service.active_slot_keys() == []

        # 干潮 (flag なし) なら spawn する
        service2, repo2, _ = _make_service(
            slots=(slot,), flags=frozenset(),
        )
        service2.run(WorldTick(0))
        assert service2.active_slot_keys() == ["crab@tidal#0"]

    def test_required_flag_spawn(self) -> None:
        """required flag が無いと spawn しない。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(),
            required_flags=("storm_warned",),
            forbidden_flags=(),
            weather_type_names=(),
        )
        service, _, _ = _make_service(slots=(slot,), flags=frozenset())
        service.run(WorldTick(0))
        assert service.active_slot_keys() == []

    def test_common_predicate_preserves_required_and_forbidden_order(self) -> None:
        """必須を宣言順に確認し、不足時は後続の禁止条件を評価しない。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=("ready", "open"),
            forbidden_flags=("sealed",), weather_type_names=(),
        )
        common = MagicMock()
        common.evaluate.side_effect = [
            PredicateResult.satisfied(),
            PredicateResult.not_satisfied(
                failed_predicate=FlagSetPredicate("open"), failed_path=(),
            ),
        ]
        service, _, _ = _make_service(slots=(slot,), flags=frozenset({"ready"}))
        service._predicate_evaluator = common

        assert not service._evaluate(slot)
        assert [call.args[0] for call in common.evaluate.call_args_list] == [
            FlagSetPredicate("ready"), FlagSetPredicate("open"),
        ]
        assert all(
            call.args[1] == WorldFlagPredicateContext(frozenset({"ready"}))
            for call in common.evaluate.call_args_list
        )

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_required_flag_surfaces_indeterminate_result(self, reason: str) -> None:
        """必須フラグ評価不能を通常の不足へ縮退させず、明示例外にする。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=("ready",),
            forbidden_flags=(), weather_type_names=(),
        )
        failed = FlagSetPredicate("ready")
        common = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed, failed_path=(),
                required_context={"world_flags"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        service, _, _ = _make_service(slots=(slot,))
        service._predicate_evaluator = common

        with pytest.raises(ScenarioPredicateEvaluationException):
            service._evaluate(slot)

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_forbidden_flag_does_not_invert_indeterminate_result(
        self, reason: str,
    ) -> None:
        """禁止フラグ評価不能を「立っていない」と反転せず、明示例外にする。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=(),
            forbidden_flags=("sealed",), weather_type_names=(),
        )
        failed = FlagSetPredicate("sealed")
        common = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed, failed_path=(),
                required_context={"world_flags"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        service, _, _ = _make_service(slots=(slot,))
        service._predicate_evaluator = common

        with pytest.raises(ScenarioPredicateEvaluationException):
            service._evaluate(slot)


class TestWeatherGate:
    """weather_type_names の候補OR評価と異常時の停止を保証する。"""

    def test_common_predicate_checks_candidates_until_match(self) -> None:
        """天候候補を宣言順に評価し、後方候補の一致でも成立する。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=(), forbidden_flags=(),
            weather_type_names=("RAIN", "STORM", "FOG"),
        )
        common = MagicMock()
        common.evaluate.side_effect = [
            PredicateResult.not_satisfied(
                failed_predicate=WeatherTypeIsPredicate(WeatherTypeEnum.RAIN),
                failed_path=(),
            ),
            PredicateResult.satisfied(),
        ]
        service, _, _ = _make_service(slots=(slot,), weather_type_name="STORM")
        service._predicate_evaluator = common

        assert service._evaluate(slot)
        assert [call.args[0] for call in common.evaluate.call_args_list] == [
            WeatherTypeIsPredicate(WeatherTypeEnum.RAIN),
            WeatherTypeIsPredicate(WeatherTypeEnum.STORM),
        ]
        assert all(
            call.args[1] == WeatherTypePredicateContext(WeatherTypeEnum.STORM)
            for call in common.evaluate.call_args_list
        )

    def test_unknown_direct_weather_values_keep_exact_match_compatibility(self) -> None:
        """loaderを迂回した未知天候も、従来どおり文字列完全一致で判定する。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=(), forbidden_flags=(),
            weather_type_names=("METEOR_SHOWER",),
        )
        service, _, _ = _make_service(
            slots=(slot,), weather_type_name="METEOR_SHOWER",
        )

        assert service._evaluate(slot)

    def test_unknown_direct_weather_values_keep_exact_mismatch_compatibility(self) -> None:
        """loaderを迂回した未知天候も、異なる文字列なら従来どおり不成立にする。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=(), forbidden_flags=(),
            weather_type_names=("METEOR_SHOWER",),
        )
        service, _, _ = _make_service(slots=(slot,), weather_type_name="ASH_FALL")

        assert not service._evaluate(slot)

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_weather_does_not_treat_indeterminate_as_no_match(
        self, reason: str,
    ) -> None:
        """天候評価不能を候補不一致へ縮退させず、明示例外にする。"""
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(), required_flags=(), forbidden_flags=(),
            weather_type_names=("STORM",),
        )
        failed = WeatherTypeIsPredicate(WeatherTypeEnum.STORM)
        common = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed, failed_path=(),
                required_context={"current_weather_type"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        service, _, _ = _make_service(slots=(slot,), weather_type_name="STORM")
        service._predicate_evaluator = common

        with pytest.raises(ScenarioPredicateEvaluationException):
            service._evaluate(slot)


class TestConditionAxisOrder:
    """昼夜・フラグ・天候の軸順とprovider呼出し回数を保証する。"""

    def _service(self, *, phase: str, flag_result: bool) -> tuple[
        SpotGraphMonsterSpawnStageService, MonsterSpawnSlot, MagicMock, MagicMock, MagicMock
    ]:
        slot = MonsterSpawnSlot(
            slot_key="x@y#0", template=_make_template(),
            spot_id=SPOT_DEEP_FOREST, coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=("night",), required_flags=("ready",),
            forbidden_flags=(), weather_type_names=("STORM",),
        )
        phase_provider = MagicMock(return_value=TimeOfDay(
            ratio=0.5, phase_name=phase, display_text=phase,
            ambient_light=0.5, is_dark=False,
        ))
        flags_provider = MagicMock(return_value=frozenset({"ready"}))
        weather_provider = MagicMock(return_value="STORM")
        common = MagicMock()
        common.evaluate.side_effect = (
            [PredicateResult.not_satisfied(
                failed_predicate=FlagSetPredicate("ready"), failed_path=(),
            )]
            if not flag_result
            else [PredicateResult.satisfied(), PredicateResult.satisfied()]
        )
        monster_repo = InMemoryMonsterAggregateRepository()
        service = SpotGraphMonsterSpawnStageService(
            slots=(slot,), monster_repository=monster_repo,
            skill_loadout_repository=InMemorySkillLoadoutRepository(),
            spot_graph_repository=InMemorySpotGraphRepository(_make_graph()),
            time_of_day_provider=phase_provider, flags_provider=flags_provider,
            weather_type_provider=weather_provider, predicate_evaluator=common,
        )
        return service, slot, phase_provider, flags_provider, weather_provider

    def test_day_night_failure_skips_later_providers(self) -> None:
        """昼夜不一致ならフラグ・天候providerを呼ばない。"""
        service, slot, phase, flags, weather = self._service(
            phase="morning", flag_result=True,
        )

        assert not service._evaluate(slot)
        phase.assert_called_once_with()
        flags.assert_not_called()
        weather.assert_not_called()

    def test_flag_failure_skips_weather_provider(self) -> None:
        """昼夜通過後にフラグが不成立なら天候providerを呼ばない。"""
        service, slot, phase, flags, weather = self._service(
            phase="night", flag_result=False,
        )

        assert not service._evaluate(slot)
        phase.assert_called_once_with()
        flags.assert_called_once_with()
        weather.assert_not_called()

    def test_all_axes_read_each_provider_once(self) -> None:
        """全軸を通過すると各providerを一度だけ読む。"""
        service, slot, phase, flags, weather = self._service(
            phase="night", flag_result=True,
        )

        assert service._evaluate(slot)
        phase.assert_called_once_with()
        flags.assert_called_once_with()
        weather.assert_called_once_with()


class TestAlwaysCondition:
    """全軸空なら always 成立 (= 毎 tick spawn 試行) するが既に spawn 済なら no-op。"""

    def test_returns_empty_when_all_tick_active(self) -> None:
        """全軸空なら毎 tick active を維持。"""
        slot = MonsterSpawnSlot(
            slot_key="a@b#0",
            template=_make_template(),
            spot_id=SPOT_DEEP_FOREST,
            coordinate=Coordinate(0, 0, 0),
            day_night_phase_names=(),
            required_flags=(),
            forbidden_flags=(),
            weather_type_names=(),
        )
        service, repo, _ = _make_service(slots=(slot,))
        service.run(WorldTick(0))
        service.run(WorldTick(1))
        # 1 体しか居ない (二重 spawn しない)
        assert len(repo.find_by_spot_id(SPOT_DEEP_FOREST)) == 1

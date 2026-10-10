"""初期配置で同じ場所にいた相手を、Being が最初から会った相手として持つことを保証する。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestAcquaintancesAtSpawn:
    """create_world_runtime が、初期配置の同席を知り合いの記録に残すことを保証する。"""

    def test_players_spawned_together_have_met_each_other_at_turn_zero(self) -> None:
        """島 (4 人が同じ浜から始まる) では、各自が他の 3 人とターン 0 に 1 回会ったことになっていて、自分は含まない。"""
        runtime = create_world_runtime(_SCENARIOS / "survival_island_v4_coop.json")
        names = {pid: runtime.get_player_name(pid) for pid in runtime.get_player_ids()}

        for pid, own_name in names.items():
            others = sorted(n for n in names.values() if n != own_name)
            met = [runtime._player_acquaintances.find(pid, n) for n in others]
            assert all(m is not None for m in met), (own_name, met)
            assert {(m.first_met_turn, m.met_count) for m in met} == {(0, 1)}
            assert runtime._player_acquaintances.find(pid, own_name) is None

    def test_players_spawned_apart_have_not_met(self) -> None:
        """別々の場所から始まる禁書庫では、紹介で互いを知ってはいるが、起動直後にはまだ会っていない。"""
        runtime = create_world_runtime(_SCENARIOS / "forbidden_library_demo.json")
        kaito, rin = runtime.get_player_ids()[:2]

        for viewer, other in ((kaito, "リン"), (rin, "カイト")):
            known = runtime._player_acquaintances.find(viewer, other)
            assert known is not None and known.met_count == 0


class TestRestoreOverSpawnRecords:
    """snapshot を読み込むと、起動時に記録した同席が、保存した知り合いの記録で置き換わることを保証する。"""

    def test_restored_records_replace_spawn_records(self, tmp_path: Path) -> None:
        """2 回会ったノアだけを知っていた Being を、4 人同席で起動した島に戻すと、知り合いはノアの 1 件で、回数は保存した 2 のままになる。"""
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        island = _SCENARIOS / "survival_island_v4_coop.json"
        source = create_world_runtime(island)
        ada = source.get_player_ids()[0]
        being_id = source.aux_being_resolver.resolve_being_id(
            source.aux_being_default_world_id, ada
        )
        source._acquaintance_store.replace_all_by_being(being_id, [])
        source._player_acquaintances.record_meeting(ada, "ノア")
        source._player_acquaintances.record_meeting(ada, "ノア")
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(source),
            snapshot_dir=tmp_path,
        ).capture_all([ada])

        restored = create_world_runtime(island)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(restored),
            snapshot_dir=tmp_path,
        ).restore_all_from_dir(tmp_path)

        met = restored._acquaintance_store.list_by_being(being_id)
        assert [(m.name, m.met_count) for m in met] == [("ノア", 2)]


class TestStartupDoesNotSpendTheWarning:
    """起動時の検査より前に Being を用意し、Being 無しの警告を誤報で使い切らないことを保証する。"""

    def test_creating_runtime_warns_no_missing_being(self, caplog) -> None:
        """station_drill を既定の設定で起動しても、「結び付く Being が無く」の警告は 1 件も出ない。"""
        import logging

        with caplog.at_level(logging.WARNING):
            create_world_runtime(_SCENARIOS / "station_drill.json")

        assert not [r for r in caplog.records if "結び付く Being が無く" in r.getMessage()]

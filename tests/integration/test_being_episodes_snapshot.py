"""世界の runtime が持つ目次つきのエピソードが、実験の snapshot を通って別の runtime に戻ることを保証する。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestBeingEpisodesCrossRuns:
    """実験の runner が使う wiring stub と ExperimentSnapshotSession が、目次つきのエピソードを拾って書き戻すことを保証する。"""

    def test_episodes_written_in_one_runtime_come_back_in_another(self, tmp_path: Path) -> None:
        """1 つ目の runtime で Being に足したエピソードは、保存して別の runtime に読み込むと、呼び出された回数と目次の履歴ごと同じ並びで戻る。"""
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
        episode = (
            Episode.write(
                episode_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
                environment_name="島",
                written_turn=2,
                index=EpisodeIndex(summary="浜で火をおこした", recall_when="寒いとき"),
                body="流木を集めて火をおこした。",
            )
            .recalled_at(turn=4)
            .with_revised_index(
                EpisodeIndex(summary="流木で火をおこした", recall_when="火が要るとき"), turn=5
            )
        )
        source._being_episode_store.add(being_id, episode)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(source),
            snapshot_dir=tmp_path,
        ).capture_all([ada])

        restored = create_world_runtime(island)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(restored),
            snapshot_dir=tmp_path,
        ).restore_all_from_dir(tmp_path)

        assert restored._being_episode_store.list_by_being(being_id) == (episode,)

"""世界の runtime が持つメモ帳が、実験の snapshot を通って別の runtime に戻ることを保証する。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.memo_book import (
    MemoBook,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestBeingMemoBookCrossRuns:
    """実験の runner が使う wiring stub と ExperimentSnapshotSession が、メモ帳を拾って書き戻すことを保証する。"""

    def test_memo_book_written_in_one_runtime_comes_back_in_another(self, tmp_path: Path) -> None:
        """1 つ目の runtime で Being のメモ帳に書いたメモは、保存して別の runtime に読み込むと、出どころと書き換えた時ごと同じ並びで戻る。"""
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
        book = MemoBook.empty(being_id)
        book.add(
            memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
            kind=MemoKind.FACT,
            text="浜の流木は乾いている",
            provenance=MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.SURE),
            turn=2,
            environment_name="島",
        )
        book.edit("m_3f2a7b", text="浜の流木はよく燃える", turn=4)
        source._being_memo_store.save(book)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(source),
            snapshot_dir=tmp_path,
        ).capture_all([ada])

        restored = create_world_runtime(island)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(restored),
            snapshot_dir=tmp_path,
        ).restore_all_from_dir(tmp_path)

        assert restored._being_memo_store.get(being_id).memos == book.memos

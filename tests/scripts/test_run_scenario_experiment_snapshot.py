"""scripts/run_scenario_experiment.py の Phase 6 snapshot 統合テスト。

実 WorldRuntime を立てる integration は LLM が要るため、ここでは
プラグの正しさだけを確認する:

- ``_wiring_stub_from_world_runtime`` が runtime の private 属性を正しく拾う
- ``--snapshot-save-dir`` / ``--snapshot-load-dir`` の argparse が通る
- ``--snapshot-load-dir`` が存在しないと parser.error で exit する

``TestExpectedPayloadKeysCoverage`` は CLAUDE.md checklist #27 (per-Being
store 追加時は snapshot 配線まで 1 PR にまとめる) の追従漏れを構造で検出する
契約テスト。episodic_stack / runtime が持つ全 store を stub 経由で
``ExperimentSnapshotSession`` まで運べているかを、fallback ログの有無で確認
する。過去に recall_slot_store / afterglow_store / recall_habituation_store
(想起階層 3 store) が拾われずに空 fallback へ倒れていた実欠落を検出できる
形で書いている。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _wiring_stub_from_world_runtime,
    main,
)


class TestWiringStub:
    """``_wiring_stub_from_world_runtime`` の attribute pickup。"""

    def test_runtime_の_private_属性を拾う(self) -> None:
        # 既存の WorldRuntime と同じ名前で attribute を立てる。
        # ``aux_being_resolver`` は public property、``_aux_being_repository``
        # は private 属性として直接読む (= helper の現実装に合わせる)。
        episode_store = object()
        runtime = SimpleNamespace(
            _todo_store="memo-handle",
            _aux_being_repository="repo-handle",
            aux_being_resolver="resolver-handle",
            _episodic_stack=SimpleNamespace(episode_store=episode_store),
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.memo_store == "memo-handle"
        assert stub.being_repository == "repo-handle"
        assert stub.being_attachment_resolver == "resolver-handle"
        assert stub.episodic_episode_store is episode_store
        # 他 5 store は world_runtime 経路では拾えないので None
        assert stub.semantic_memory_store is None
        assert stub.memory_link_store is None
        assert stub.episodic_recall_buffer_store is None
        assert stub.episodic_reinterpretation_journal_store is None
        # U2: episodic_stack が belief_evidence_buffer_store を持たない
        # (= BELIEF_EVIDENCE_ENABLED OFF) なら None。
        assert stub.belief_evidence_buffer_store is None

    def test_belief_evidence_buffer_store_が_episodic_stack_にあれば拾う(
        self,
    ) -> None:
        """U2 (証拠台帳統一設計): BELIEF_EVIDENCE_ENABLED ON のとき
        episodic_stack が持つ belief_evidence_buffer_store を stub が拾う。
        拾い忘れると flag ON でも evidence が snapshot に乗らず、save/load で
        silent に失われる (checklist #27 の教訓)。"""
        belief_evidence_buffer_store = object()
        runtime = SimpleNamespace(
            _todo_store="memo-handle",
            _aux_being_repository="repo-handle",
            aux_being_resolver="resolver-handle",
            _episodic_stack=SimpleNamespace(
                episode_store=object(),
                belief_evidence_buffer_store=belief_evidence_buffer_store,
            ),
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.belief_evidence_buffer_store is belief_evidence_buffer_store

    def test_想起階層_3_store_が_episodic_stack_にあれば拾う(self) -> None:
        """PR-G (想起階層: slot / afterglow / habituation) の 3 store が
        episodic_stack にあるとき stub が拾うことを保証する。

        これらは checklist #27 の追従漏れが実際に発生していた箇所:
        belief_evidence_buffer_store 等より後に ``EpisodicStack`` に生えたが、
        この stub 側の pickup が追加されないまま残り、実験の save/load で
        slot / afterglow / habituation の状態が無音で失われていた。
        """
        recall_slot_store = object()
        afterglow_store = object()
        recall_habituation_store = object()
        runtime = SimpleNamespace(
            _todo_store="memo-handle",
            _aux_being_repository="repo-handle",
            aux_being_resolver="resolver-handle",
            _episodic_stack=SimpleNamespace(
                episode_store=object(),
                recall_slot_store=recall_slot_store,
                afterglow_store=afterglow_store,
                recall_habituation_store=recall_habituation_store,
            ),
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.recall_slot_store is recall_slot_store
        assert stub.afterglow_store is afterglow_store
        assert stub.recall_habituation_store is recall_habituation_store

    def test_episodic_stack_が_None_なら_episode_store_も_None(self) -> None:
        runtime = SimpleNamespace(
            _todo_store=None,
            _aux_being_repository=None,
            aux_being_resolver=None,
            _episodic_stack=None,
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.episodic_episode_store is None

    def test_どの_attribute_も_欠落なら_None_を返す(self) -> None:
        """getattr の default 経由で SimpleNamespace ですらない object でも壊れない。"""

        class _Bare:
            pass

        stub = _wiring_stub_from_world_runtime(_Bare())
        assert stub.memo_store is None
        assert stub.being_repository is None
        assert stub.being_attachment_resolver is None
        assert stub.episodic_episode_store is None


class TestExpectedPayloadKeysCoverage:
    """checklist #27 の追従漏れを構造で検出する契約テスト。

    ``BeingMemorySnapshotService`` が対応する per-Being store が
    ``episodic_stack`` / ``runtime`` 側に揃っているにもかかわらず、
    ``_wiring_stub_from_world_runtime`` がそれを拾い忘れていると
    ``ExperimentSnapshotSession`` は空 in-memory store に fallback する
    (= 実験の save/load でその store の状態が無音で失われる)。

    このテストは「stub が拾うべき store 名の一覧」を
    ``ExperimentSnapshotSession`` の fallback 監視対象リストと同じ形で持ち、
    episodic_stack 側に **全部揃っている** 状態を作って
    ``ExperimentSnapshotSession`` を構築し、fallback ログが 1 件も出ない
    ことを確認する。新しい per-Being store を追加したのに stub 側の pickup
    を足し忘れると、このテストが red で知らせる。
    """

    def test_episodic_stack_の全_store_が_fallback_なしで配線される(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )
        from ai_rpg_world.application.llm.services.afterglow_store import (
            InMemoryAfterglowStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            InMemoryEpisodicRecallSlotStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
            InMemoryMemoryLinkStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
            InMemoryEpisodicReinterpretationJournalStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
            InMemoryGoalJournalStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_memo_store import (
            InMemoryMemoStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
            InMemoryPendingPredictionStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
            InMemorySemanticMemoryStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        repo = InMemoryBeingRepository()
        # episodic_stack 側の attribute 名は EpisodicStack dataclass (実体) と
        # 揃える。reinterpretation_journal だけ stub 内部で
        # ``episodic_reinterpretation_journal_store`` にリネームされる
        # (既存の semantic / memory_link / recall_buffer と同じ扱い)。
        episodic_stack = SimpleNamespace(
            episode_store=InMemorySubjectiveEpisodeStore(),
            semantic_memory_store=InMemorySemanticMemoryStore(),
            memory_link_store=InMemoryMemoryLinkStore(),
            recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
            reinterpretation_journal=InMemoryEpisodicReinterpretationJournalStore(),
            belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(),
            recall_success_store=InMemoryEpisodicRecallSuccessStore(),
            pending_prediction_store=InMemoryPendingPredictionStore(),
            recall_slot_store=InMemoryEpisodicRecallSlotStore(),
            afterglow_store=InMemoryAfterglowStore(),
            recall_habituation_store=InMemoryEpisodicRecallHabituationStore(),
        )
        runtime = SimpleNamespace(
            _todo_store=InMemoryMemoStore(),
            _aux_being_repository=repo,
            aux_being_resolver=BeingAttachmentResolver(repo),
            _episodic_stack=episodic_stack,
            _goal_journal_store=InMemoryGoalJournalStore(),
        )

        wiring_stub = _wiring_stub_from_world_runtime(runtime)

        with caplog.at_level("INFO"):
            ExperimentSnapshotSession(
                wiring_result=wiring_stub, snapshot_dir=tmp_path / "snap"
            )

        fallback_logs = [
            r
            for r in caplog.records
            if "empty in-memory fallback" in r.message
        ]
        assert fallback_logs == [], (
            "episodic_stack / runtime に store があるのに stub が拾えず "
            f"fallback している: {fallback_logs[0].args if fallback_logs else None}"
        )


class TestSnapshotArgs:
    """snapshot 関連の argparse / 早期 validation。"""

    def test_snapshot_load_dir_が_存在しないと_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        missing = tmp_path / "no-such-dir"
        with pytest.raises(SystemExit) as excinfo:
            main(
                [
                    "--scenario",
                    str(scenario),
                    "--max-world-ticks",
                    "1",
                    "--out",
                    str(tmp_path / "out"),
                    "--snapshot-load-dir",
                    str(missing),
                ]
            )
        # argparse は SystemExit(2) を投げる
        assert excinfo.value.code == 2
        captured = capsys.readouterr()
        assert "snapshot-load-dir" in captured.err

    def test_snapshot_save_dir_を_受け取れる(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """argparse で --snapshot-save-dir が解釈され、_drive_scenario に渡る。

        実 simulation は走らせず、_drive_scenario を mock して引数だけ確認する。
        """
        import scripts.run_scenario_experiment as runner

        captured: dict = {}

        def _fake_drive(**kwargs):
            captured.update(kwargs)
            return {
                "outcome": "TIMEOUT",
                "last_tick": 0,
                "elapsed_sec": 0.0,
                "max_world_ticks": 1,
                "snapshot_save_dir": (
                    str(kwargs.get("snapshot_save_dir"))
                    if kwargs.get("snapshot_save_dir")
                    else None
                ),
                "snapshot_load_dir": None,
            }

        monkeypatch.setattr(runner, "_drive_scenario", _fake_drive)
        monkeypatch.setattr(runner, "_emit_html", lambda *a, **kw: None)

        scenario = tmp_path / "demo.json"
        scenario.write_text("{}", encoding="utf-8")
        save_dir = tmp_path / "snap"
        rc = main(
            [
                "--scenario",
                str(scenario),
                "--max-world-ticks",
                "1",
                "--out",
                str(tmp_path / "out"),
                "--snapshot-save-dir",
                str(save_dir),
                "--no-html",
                "--no-progress-jsonl",
                "--no-stderr-progress",
            ]
        )
        assert rc == 0
        # 受け取った drive 引数に snapshot_save_dir が乗っている。
        assert captured["snapshot_save_dir"] == save_dir
        assert captured["snapshot_load_dir"] is None
        # --snapshot-save-dir 指定時は事前に mkdir される。
        assert save_dir.exists()

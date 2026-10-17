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
する。過去に想起階層の 3 store (#1631 で消した) が拾われずに空 fallback へ
倒れていた実欠落を検出できる形で書いている。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _wiring_stub_from_world_runtime,
    main,
)


class TestWiringStub:
    """``_wiring_stub_from_world_runtime`` の attribute pickup。"""

    def test_finds_runtime_private_attribute(self) -> None:
        """runtime の private 属性を拾う。"""
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
        # link store は episodic stack が持たないので None
        assert stub.memory_link_store is None

    def test_episodic_stack_none_episode_store_none(self) -> None:
        """episodic stack が None なら episode store も None。"""
        runtime = SimpleNamespace(
            _todo_store=None,
            _aux_being_repository=None,
            aux_being_resolver=None,
            _episodic_stack=None,
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.episodic_episode_store is None

    def test_returns_none_attribute_missing(self) -> None:
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

    逆向きの相棒テスト (store を 1 つ欠いた状態で fallback ログが実際に出る)
    も併せて持つ。「fallback ログ 0 件」の判定は
    ``_FALLBACK_LOG_MARKER`` の文字列一致に依存しているため、将来
    ``experiment_snapshot_session.py`` のログ文言が変わると本体テストは
    何も検出しないまま緑になり続ける (ガード自身の静かな失敗)。相棒テスト
    が同じ文字列で「出るべき時に出る」ことを主張することで、文言が変われば
    相棒側が赤になり、検出機構が生きていることを常に保証する。
    """

    # ExperimentSnapshotSession の fallback ログ文言と一致させるマーカー。
    # 文言が変わると test_store_を_1_つ欠くと_fallback_ログが出る が赤に
    # なるので、そのときは両テストとこのマーカーを一緒に更新する。
    _FALLBACK_LOG_MARKER = "empty in-memory fallback"

    @staticmethod
    def _runtime_stub_with_all_stores() -> SimpleNamespace:
        """BeingMemorySnapshotService が対応する全 per-Being store を
        episodic_stack / runtime に揃えた runtime stub を作る。"""
        from ai_rpg_world.application.being.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
            InMemoryMemoryLinkStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_memo_store import (
            InMemoryMemoStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
            InMemoryAcquaintanceRepository,
        )
        from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
            InMemoryEpisodeRepository,
        )
        from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import (
            InMemoryMemoBookRepository,
        )
        from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
            InMemoryMemoryTurnClock,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        repo = InMemoryBeingRepository()
        # episodic_stack 側の attribute 名は EpisodicStack dataclass (実体) と
        # 揃える。
        episodic_stack = SimpleNamespace(
            episode_store=InMemorySubjectiveEpisodeStore(),
            memory_link_store=InMemoryMemoryLinkStore(),
            )
        return SimpleNamespace(
            _todo_store=InMemoryMemoStore(),
            _aux_being_repository=repo,
            aux_being_resolver=BeingAttachmentResolver(repo),
            _episodic_stack=episodic_stack,
            _memory_turn_clock=InMemoryMemoryTurnClock(),
            _acquaintance_store=InMemoryAcquaintanceRepository(),
            _being_episode_store=InMemoryEpisodeRepository(),
            _being_memo_store=InMemoryMemoBookRepository(),
        )

    def _fallback_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> list[object]:
        return [
            r
            for r in caplog.records
            if self._FALLBACK_LOG_MARKER in r.message
        ]

    def test_episodic_stack_all_store_fallback_wired(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """episodic_stack / runtime に全 store が揃っていれば、stub 経由で
        ExperimentSnapshotSession を構築しても空 in-memory fallback のログが
        1 件も出ない (= 追従漏れの store が無い)。"""
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        runtime = self._runtime_stub_with_all_stores()
        wiring_stub = _wiring_stub_from_world_runtime(runtime)

        with caplog.at_level("INFO"):
            ExperimentSnapshotSession(
                wiring_result=wiring_stub, snapshot_dir=tmp_path / "snap"
            )

        fallback_logs = self._fallback_logs(caplog)
        assert fallback_logs == [], (
            "episodic_stack / runtime に store があるのに stub が拾えず "
            f"fallback している: {fallback_logs[0].args if fallback_logs else None}"
        )

    def test_store_one_fallback_log_rendered(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """episodic_stack から store を 1 つ欠いた状態では、fallback ログが
        ``_FALLBACK_LOG_MARKER`` の文字列で実際に 1 件以上出る。

        本体テスト (fallback ログ 0 件で緑) の検出機構が文字列一致に依存する
        ため、ログ文言が変わると本体テストは無検出のまま緑になり続ける。
        この相棒テストは「出るべき時にその文字列で出る」ことを主張し、文言が
        変わればこちらが赤になることで、検出機構が生きていることを保証する。
        """
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        runtime = self._runtime_stub_with_all_stores()
        # 1 store を欠く = stub は None を渡し、session が
        # 空 in-memory fallback に倒れてログを出すはず。
        del runtime._episodic_stack.memory_link_store

        wiring_stub = _wiring_stub_from_world_runtime(runtime)
        assert wiring_stub.memory_link_store is None

        with caplog.at_level("INFO"):
            ExperimentSnapshotSession(
                wiring_result=wiring_stub, snapshot_dir=tmp_path / "snap"
            )

        fallback_logs = self._fallback_logs(caplog)
        assert len(fallback_logs) >= 1, (
            "store を欠いたのに fallback ログが出ない。"
            "experiment_snapshot_session.py のログ文言が変わった場合は "
            "_FALLBACK_LOG_MARKER と本体テストを一緒に更新すること。"
        )
        # 欠いた store 名がログの引数 (fallback 対象リスト) に含まれる。
        assert any(
            "memory_link_store" in str(r.args) for r in fallback_logs
        )


class TestSnapshotArgs:
    """snapshot 関連の argparse / 早期 validation。"""

    def test_snapshot_load_dir_exit_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """snapshotloaddir が存在しないと exit2。"""
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

    def test_snapshot_save_dir_can_get(
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


class TestSnapshotTraceCarriesMemoryTurns:
    """smoke_stub で保存と再開を通しで回し、SNAPSHOT_SAVE / SNAPSHOT_LOAD の trace に Being ごとの記憶のターン数が載ることを保証する。"""

    @staticmethod
    def _events(trace_path: Path, kind: str) -> list[dict]:
        import json

        lines = trace_path.read_text(encoding="utf-8").splitlines()
        return [e for e in map(json.loads, lines) if e["kind"] == kind]

    def test_save_and_load_traces_carry_memory_turns(self, tmp_path: Path) -> None:
        """保存した Being と復元した Being ごとに記憶のターン数が載り、1 手ごとに進んだ値が再開のあとも同じ値で戻る。"""
        from scripts.run_scenario_experiment import main

        common = ["--profile", "smoke_stub", "--max-world-ticks", "2", "--no-html", "--no-progress-jsonl", "--no-stderr-progress"]
        snapshots = tmp_path / "snapshots"
        assert main([*common, "--out", str(tmp_path / "first"), "--snapshot-save-dir", str(snapshots)]) == 0
        assert main([*common, "--out", str(tmp_path / "second"), "--snapshot-load-dir", str(snapshots)]) == 0

        (saved,) = self._events(tmp_path / "first" / "trace.jsonl", "snapshot_save")
        (loaded,) = self._events(tmp_path / "second" / "trace.jsonl", "snapshot_load")

        turns: list[dict[str, int]] = []
        for event, ids_key in ((saved, "succeeded_being_ids"), (loaded, "restored_being_ids")):
            counts = event["payload"]["memory_turns"]
            assert [c["being_id"] for c in counts] == event["payload"][ids_key]
            assert len(counts) > 0
            assert all(set(c) == {"being_id", "memory_turn"} for c in counts)
            turns.append({c["being_id"]: c["memory_turn"] for c in counts})
        assert turns[0] == turns[1]
        assert any(turn > 0 for turn in turns[0].values())

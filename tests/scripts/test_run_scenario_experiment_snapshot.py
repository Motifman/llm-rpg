"""scripts/run_scenario_experiment.py の Phase 6 snapshot 統合テスト。

実 WorldRuntime を立てる integration は LLM が要るため、ここでは
プラグの正しさだけを確認する:

- ``_wiring_stub_from_world_runtime`` が runtime の private 属性を正しく拾う
- ``--snapshot-save-dir`` / ``--snapshot-load-dir`` の argparse が通る
- ``--snapshot-load-dir`` が存在しないと parser.error で exit する

``TestExpectedPayloadKeysCoverage`` は CLAUDE.md checklist #27 (per-Being
store 追加時は snapshot 配線まで 1 PR にまとめる) の追従漏れを構造で検出する
契約テスト。runtime が持つ全 store を stub 経由で
``ExperimentSnapshotSession`` まで運べているかを確認する。
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

    def test_finds_runtime_private_attribute(self) -> None:
        """runtime の private 属性を拾う。"""
        # 既存の WorldRuntime と同じ名前で attribute を立てる。
        # ``aux_being_resolver`` は public property、``_aux_being_repository``
        # は private 属性として直接読む (= helper の現実装に合わせる)。
        runtime = SimpleNamespace(
            _aux_being_repository="repo-handle",
            aux_being_resolver="resolver-handle",
        )
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.being_repository == "repo-handle"
        assert stub.being_attachment_resolver == "resolver-handle"
        assert not hasattr(stub, "episodic_episode_store")

    def test_returns_none_attribute_missing(self) -> None:
        """getattr の default 経由で SimpleNamespace ですらない object でも壊れない。"""

        class _Bare:
            pass

        stub = _wiring_stub_from_world_runtime(_Bare())
        assert stub.being_repository is None
        assert stub.being_attachment_resolver is None


class TestExpectedPayloadKeysCoverage:
    """checklist #27 の追従漏れを構造で検出する契約テスト。

    ``ExperimentSnapshotSession`` は、Being の記憶の store が 1 つでも渡らない
    と起動時に止まる。runtime に全 store が揃っているときに stub がそれを
    拾い忘れていれば、ここで止まって知らせる。
    """

    @staticmethod
    def _runtime_stub_with_all_stores() -> SimpleNamespace:
        """BeingMemorySnapshotService が対応する全 per-Being store を
        runtime に揃えた runtime stub を作る。"""
        from ai_rpg_world.application.being.being_attachment_resolver import (
            BeingAttachmentResolver,
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
        from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
            InMemoryShortTermMemoryRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        repo = InMemoryBeingRepository()
        return SimpleNamespace(
            _aux_being_repository=repo,
            aux_being_resolver=BeingAttachmentResolver(repo),
            _memory_turn_clock=InMemoryMemoryTurnClock(),
            _acquaintance_store=InMemoryAcquaintanceRepository(),
            _being_episode_store=InMemoryEpisodeRepository(),
            _being_memo_store=InMemoryMemoBookRepository(),
            _being_short_term_memory_store=InMemoryShortTermMemoryRepository(),
        )

    def test_runtime_with_all_stores_builds_a_session(self, tmp_path: Path) -> None:
        """runtime に全 store が揃っていれば、stub 経由で ExperimentSnapshotSession を組める。"""
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        wiring_stub = _wiring_stub_from_world_runtime(self._runtime_stub_with_all_stores())

        ExperimentSnapshotSession(wiring_result=wiring_stub, snapshot_dir=tmp_path / "snap")

    @pytest.mark.parametrize(
        ("runtime_attribute", "wiring_name"),
        [
            ("_aux_being_repository", "being_repository"),
            ("aux_being_resolver", "being_attachment_resolver"),
            ("_acquaintance_store", "acquaintance_store"),
            ("_being_episode_store", "being_episode_store"),
            ("_being_memo_store", "being_memo_store"),
            ("_memory_turn_clock", "memory_turn_clock"),
            ("_being_short_term_memory_store", "being_short_term_memory_store"),
        ],
    )
    def test_runtime_missing_one_store_stops_the_session(
        self, tmp_path: Path, runtime_attribute: str, wiring_name: str
    ) -> None:
        """runtime から store を 1 つ欠くと、空で代用せずに、欠けた名前を挙げて起動時に止まる。"""
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        runtime = self._runtime_stub_with_all_stores()
        setattr(runtime, runtime_attribute, None)
        wiring_stub = _wiring_stub_from_world_runtime(runtime)

        with pytest.raises(RuntimeError, match=wiring_name):
            ExperimentSnapshotSession(wiring_result=wiring_stub, snapshot_dir=tmp_path / "snap")


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

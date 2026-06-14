"""scripts/run_scenario_experiment.py の Phase 6 snapshot 統合テスト。

実 EscapeGameRuntime を立てる integration は LLM が要るため、ここでは
プラグの正しさだけを確認する:

- ``_wiring_stub_from_escape_runtime`` が runtime の private 属性を正しく拾う
- ``--snapshot-save-dir`` / ``--snapshot-load-dir`` の argparse が通る
- ``--snapshot-load-dir`` が存在しないと parser.error で exit する
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _wiring_stub_from_escape_runtime,
    main,
)


class TestWiringStub:
    """``_wiring_stub_from_escape_runtime`` の attribute pickup。"""

    def test_runtime_の_private_属性を拾う(self) -> None:
        # 既存の EscapeGameRuntime と同じ名前で attribute を立てる。
        # ``aux_being_resolver`` は public property、``_aux_being_repository``
        # は private 属性として直接読む (= helper の現実装に合わせる)。
        episode_store = object()
        runtime = SimpleNamespace(
            _todo_store="memo-handle",
            _aux_being_repository="repo-handle",
            aux_being_resolver="resolver-handle",
            _episodic_stack=SimpleNamespace(episode_store=episode_store),
        )
        stub = _wiring_stub_from_escape_runtime(runtime)
        assert stub.memo_store == "memo-handle"
        assert stub.being_repository == "repo-handle"
        assert stub.being_attachment_resolver == "resolver-handle"
        assert stub.episodic_episode_store is episode_store
        # 他 4 store は escape_game 経路では拾えないので None
        assert stub.semantic_memory_store is None
        assert stub.memory_link_store is None
        assert stub.episodic_recall_buffer_store is None
        assert stub.episodic_reinterpretation_journal_store is None

    def test_episodic_stack_が_None_なら_episode_store_も_None(self) -> None:
        runtime = SimpleNamespace(
            _todo_store=None,
            _aux_being_repository=None,
            aux_being_resolver=None,
            _episodic_stack=None,
        )
        stub = _wiring_stub_from_escape_runtime(runtime)
        assert stub.episodic_episode_store is None

    def test_どの_attribute_も_欠落なら_None_を返す(self) -> None:
        """getattr の default 経由で SimpleNamespace ですらない object でも壊れない。"""

        class _Bare:
            pass

        stub = _wiring_stub_from_escape_runtime(_Bare())
        assert stub.memo_store is None
        assert stub.being_repository is None
        assert stub.being_attachment_resolver is None
        assert stub.episodic_episode_store is None


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

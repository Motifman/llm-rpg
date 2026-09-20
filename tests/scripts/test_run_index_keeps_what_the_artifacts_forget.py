"""run の索引が、成果物が消えた後も条件を覚えていることを保証する。

## なぜ索引が要るか

1 本の run を詳しく見る道具は既にある (report.md / trace.html)。無いのは
**run を横断して引く手段**である。「同じ profile の run はどれか」「操作名の
失敗が多いのはどれか」を知るために、69 個のディレクトリを開いて数えていた。

## 成果物より長く生きる

``var/`` は gitignore なので、trace は worktree と一緒に消える。索引は commit
するので、**成果物が消えた後も「いつ・どの commit で・何を測ったか」が残る**。

そのため索引を作り直すとき、**手元に無い run の行を消してはいけない**。別の
機材で走らせた run や、掃除したあとの run の記録が、実行しただけで失われる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from scripts.build_run_index import build_index, read_index, write_index


def _run_dir(
    root: Path,
    name: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    run = root / name
    run.mkdir(parents=True)
    if config is not None:
        (run / "experiment.config.resolved.json").write_text(
            json.dumps(config, ensure_ascii=False)
        )
    (run / "trace.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in (events or []))
    )
    return run


def _config(**overrides: Any) -> Dict[str, Any]:
    base = {
        "profile": "belief_goal_full",
        "scenario_path": "data/scenarios/survival_island_v2.json",
        "scenario_sha256": "a" * 64,
        "max_world_ticks": 80,
        "git": {"commit": "b" * 40, "dirty": False},
        "runtime_config": {"llm_model": "openrouter/deepseek/deepseek-v4-flash"},
    }
    base.update(overrides)
    return base


def _action(error_code: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"tool": "interact", "success": error_code is None}
    if error_code:
        payload["error_code"] = error_code
    return {"kind": "action_result", "tick": 1, "player_id": 1, "payload": payload}


class TestOneRowPerRun:
    """run 1 本が 1 行になり、後から引ける列を持つことを保証する。"""

    def test_a_run_becomes_one_row(self, tmp_path: Path) -> None:
        """trace を持つ run が 1 行になる。"""
        _run_dir(tmp_path, "r1", config=_config(), events=[_action()])

        rows = build_index(tmp_path)

        assert len(rows) == 1
        assert rows[0]["id"] == "r1"
        assert rows[0]["kind"] == "run"

    def test_the_row_carries_the_conditions_of_the_measurement(
        self, tmp_path: Path
    ) -> None:
        """どの commit・どの profile・どのシナリオで走ったかが列に入る。"""
        _run_dir(tmp_path, "r1", config=_config(), events=[_action()])

        row = build_index(tmp_path)[0]

        assert row["git_commit"] == "b" * 40
        assert row["profile"] == "belief_goal_full"
        assert row["scenario"] == "survival_island_v2.json"
        assert row["scenario_sha256"] == "a" * 64
        assert row["max_world_ticks"] == 80
        assert row["model"] == "openrouter/deepseek/deepseek-v4-flash"

    def test_the_row_counts_failures_by_code(self, tmp_path: Path) -> None:
        """失敗を error_code ごとに数える。横断で「どの失敗が多いか」を引ける。"""
        _run_dir(
            tmp_path,
            "r1",
            config=_config(),
            events=[
                _action(),
                _action("INTERACTION_ACTION_NOT_FOUND"),
                _action("INTERACTION_ACTION_NOT_FOUND"),
                _action("INTERACTION_PRECONDITION_FAILED"),
            ],
        )

        row = build_index(tmp_path)[0]

        assert row["metrics"]["action_results"] == 4
        assert row["metrics"]["action_failures"] == 3
        assert row["metrics"]["failures_by_code"] == {
            "INTERACTION_ACTION_NOT_FOUND": 2,
            "INTERACTION_PRECONDITION_FAILED": 1,
        }

    def test_a_run_without_a_config_is_still_listed(self, tmp_path: Path) -> None:
        """設定ファイルが無い run も行にする。

        **黙って落とすと、索引が『全部ある』ように見える。** 条件を復元できない
        run が在ることまで含めて記録する。
        """
        _run_dir(tmp_path, "manual", events=[_action()])

        row = build_index(tmp_path)[0]

        assert row["id"] == "manual"
        assert row["git_commit"] is None
        assert row["conditions_recoverable"] is False

    def test_a_run_with_a_config_is_marked_recoverable(self, tmp_path: Path) -> None:
        """設定ファイルがある run は、条件を復元できると印が付く (**正の対照**)。"""
        _run_dir(tmp_path, "r1", config=_config(), events=[_action()])

        assert build_index(tmp_path)[0]["conditions_recoverable"] is True

    def test_a_directory_without_a_trace_is_skipped(self, tmp_path: Path) -> None:
        """trace が無いディレクトリは run ではない。"""
        (tmp_path / "not_a_run").mkdir()

        assert build_index(tmp_path) == []

    def test_a_broken_trace_line_does_not_stop_the_scan(self, tmp_path: Path) -> None:
        """壊れた行があっても、その run を落とさず読める分だけ数える。

        途中で例外にすると、1 行の破損で索引全体が作れなくなる。
        """
        run = _run_dir(tmp_path, "r1", config=_config(), events=[_action()])
        with (run / "trace.jsonl").open("a") as handle:
            handle.write("\n{壊れた行\n")

        row = build_index(tmp_path)[0]

        assert row["metrics"]["action_results"] == 1
        assert row["metrics"]["unreadable_lines"] == 1


class TestTheIndexOutlivesTheArtifacts:
    """手元に無い run の行を、作り直しで失わないことを保証する。"""

    def test_an_existing_row_survives_a_rebuild(self, tmp_path: Path) -> None:
        """手元に成果物が無い run の行は、作り直しても残る。

        別の機材で走らせた run や、掃除したあとの run の記録が、索引を作り
        直しただけで消えてはいけない。
        """
        index = tmp_path / "run_index.jsonl"
        write_index(index, [{"kind": "run", "id": "gone", "git_commit": "c" * 40}])
        runs = tmp_path / "runs"
        runs.mkdir()
        _run_dir(runs, "here", config=_config(), events=[_action()])

        merged = write_index(index, build_index(runs), merge=True)

        assert sorted(r["id"] for r in merged) == ["gone", "here"]

    def test_a_rebuilt_row_replaces_the_old_one(self, tmp_path: Path) -> None:
        """同じ run を作り直したら、行は増えずに置き換わる。"""
        index = tmp_path / "run_index.jsonl"
        write_index(index, [{"kind": "run", "id": "here", "git_commit": "old"}])
        runs = tmp_path / "runs"
        runs.mkdir()
        _run_dir(runs, "here", config=_config(), events=[_action()])

        merged = write_index(index, build_index(runs), merge=True)

        assert len(merged) == 1
        assert merged[0]["git_commit"] == "b" * 40

    def test_rows_are_written_one_per_line(self, tmp_path: Path) -> None:
        """1 行 1 件で書く。grep と jq で引けることが索引の目的なので。"""
        index = tmp_path / "run_index.jsonl"
        write_index(
            index, [{"kind": "run", "id": "a"}, {"kind": "run", "id": "b"}]
        )

        lines = index.read_text().strip().splitlines()

        assert len(lines) == 2
        assert [json.loads(line)["id"] for line in lines] == ["a", "b"]

    def test_rows_are_ordered_by_id(self, tmp_path: Path) -> None:
        """並びを id で固定する。作り直すたびに差分が出ると commit が読めない。"""
        index = tmp_path / "run_index.jsonl"
        write_index(index, [{"kind": "run", "id": "b"}, {"kind": "run", "id": "a"}])

        assert [r["id"] for r in read_index(index)] == ["a", "b"]

    def test_a_row_without_an_id_is_rejected(self, tmp_path: Path) -> None:
        """id の無い行は書かない。置き換えの基準が無いと重複する。"""
        with pytest.raises(ValueError):
            write_index(tmp_path / "run_index.jsonl", [{"kind": "run"}])


class TestProbesUseTheSameShape:
    """probe の結果が、run と同じ形で同じ索引に載ることを保証する。"""

    def test_a_probe_row_keeps_the_common_keys(self, tmp_path: Path) -> None:
        """kind が違うだけで、引くための列は run と同じにする。"""
        index = tmp_path / "run_index.jsonl"
        row = {
            "kind": "probe",
            "id": "jev_action_name_rescue_20260920",
            "measured_at": "2026-09-20T05:15:47+00:00",
            "git_commit": "d" * 40,
            "conditions_recoverable": True,
            "metrics": {"rescued": 71, "real_total": 99},
        }

        written = write_index(index, [row], merge=True)

        assert written[0]["kind"] == "probe"
        assert set(("kind", "id", "measured_at", "git_commit")) <= set(written[0])


class TestTheProbeRowMatchesTheRunShape:
    """probe の行が、run の行と同じ列で引けることを保証する。"""

    def test_the_probe_row_carries_the_same_columns(self, tmp_path: Path) -> None:
        """kind 以外の引くための列が run と揃う。

        揃えないと、同じ索引に載せても横断で引けない。
        """
        from scripts.jev_action_name_rescue_demo import index_row

        payload = {
            "conditions": {
                "measured_at": "2026-09-20T05:15:47+00:00",
                "git_commit": "e" * 40,
                "git_dirty": False,
                "cases_sha256": "f" * 64,
            },
            "model": "typesafe/jev-1.13",
            "variant": "full",
            "min_confidence": 0.7,
            "label_lookup": {"exact": 132},
        }
        summary = {
            "real_total": 99,
            "control_total": 99,
            "methods": {
                "jev": {"rescued": 71, "false_rescue": 10},
                "difflib": {"rescued": 14},
                "normalized": {"rescued": 2},
            },
            "control_labelled": {"wrong": 1},
        }

        row = index_row(payload, summary, tmp_path / "report.html")

        assert row["kind"] == "probe"
        assert row["conditions_recoverable"] is True
        assert row["metrics"]["rescued"] == 71
        assert row["metrics"]["false_rescue_labelled_wrong"] == 1
        for column in (
            "id",
            "measured_at",
            "git_commit",
            "git_dirty",
            "profile",
            "scenario",
            "model",
            "metrics",
            "artifacts",
        ):
            assert column in row, column

    def test_a_result_without_conditions_gets_no_recoverable_mark(
        self, tmp_path: Path
    ) -> None:
        """条件の無い結果は、復元できないと印が付く (**正の対照**)。"""
        from scripts.jev_action_name_rescue_demo import index_row

        row = index_row(
            {"conditions": {}, "model": "m"},
            {
                "real_total": 1,
                "control_total": 0,
                "methods": {
                    "jev": {"rescued": 0, "false_rescue": 0},
                    "difflib": {"rescued": 0},
                    "normalized": {"rescued": 0},
                },
            },
            tmp_path / "report.html",
        )

        assert row["conditions_recoverable"] is False

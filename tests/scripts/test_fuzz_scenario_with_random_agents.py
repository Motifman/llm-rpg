"""でたらめに行動するエージェントで回す入口が、穴を見つけて、シード・tick・行動の並びで再現できる形で出すことを保証する。

わざと穴を入れた小さなシナリオ (persistent_world_demo を元に書き換えたもの) で確かめる。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from scripts.fuzz_scenario_with_random_agents import (
    FuzzFinding,
    FuzzResult,
    KnownHole,
    TurnView,
    classify,
    find_leaks,
    run_random_agents,
    summarize,
    tool_texts,
    unreadable_candidate_lines,
)

from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime

_REPO = Path(__file__).resolve().parents[2]
_BASE = _REPO / "data" / "scenarios" / "persistent_world_demo.json"
_MINE = _REPO / "data" / "scenarios" / "mine_village_v1.json"


def _small_scenario(tmp_path: Path, mutate=None) -> Path:
    """2 部屋・2 人の小さなシナリオを書き出す。ファイル名は metadata.id と揃える。"""
    raw: dict[str, Any] = json.loads(_BASE.read_text(encoding="utf-8"))
    second = dict(raw["players"][0], id="visitor", name="旅人", spawn_spot="garden")
    raw["players"].append(second)
    if mutate is not None:
        mutate(raw)
    path = tmp_path / f"{raw['metadata']['id']}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _kinds(result: FuzzResult) -> list[str]:
    return [f.kind for f in result.findings]


class TestReproducible:
    """同じシードなら同じ行動の並びになり、失敗をシードで再現できる。"""

    def test_same_seed_gives_the_same_action_sequence(self, tmp_path: Path) -> None:
        """同じシード・同じ tick 数で 2 回回すと、tick・人・tool・引数の並びが一致する。"""
        scenario = _small_scenario(tmp_path)

        first = run_random_agents(scenario, seed=3, max_world_ticks=8)
        second = run_random_agents(scenario, seed=3, max_world_ticks=8)

        assert len(first.actions) >= 8
        assert first.actions == second.actions

    def test_different_seeds_give_different_action_sequences(self, tmp_path: Path) -> None:
        """シードを変えると並びが変わる。変わらなければ、上の一致は何も確かめていない。"""
        scenario = _small_scenario(tmp_path)

        a = run_random_agents(scenario, seed=3, max_world_ticks=8)
        b = run_random_agents(scenario, seed=4, max_world_ticks=8)

        assert a.actions != b.actions

    def test_both_players_act_and_the_run_reaches_the_tick_limit(self, tmp_path: Path) -> None:
        """例外を仕込まないシナリオでは、2 人とも行動し、決めた tick まで進み、例外を何も見つけない。"""
        scenario = _small_scenario(tmp_path)

        result = run_random_agents(scenario, seed=0, max_world_ticks=6)

        assert result.reached_tick == 6
        assert {a.player_id for a in result.actions} == {1, 2}
        assert not {"exception", "swallowed_exception", "logged_error"} & set(_kinds(result))

    def test_a_run_without_findings_is_reported_as_ok(self) -> None:
        """何も見つけなかった run は、OK とシナリオ・シード・tick 数の 1 行で出す。"""
        result = FuzzResult("s", 5, 10, reached_tick=10)

        assert result.report() == "OK   s seed=5 ticks=10 reached=10 actions=0"


class TestDetectsExceptions:
    """例外で止まる組み合わせを見つけて、tick と直前の行動を出す。"""

    def test_exception_out_of_advance_tick_is_reported_with_tick_and_actions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """世界の進行が 3 回目に例外を投げると、tick 2 で止まった失敗として、例外の型と直前の行動の並びを出す。"""
        original = SpotGraphSimulationApplicationService.tick
        calls = {"n": 0}

        def broken_tick(self):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("仕込んだ例外")
            return original(self)

        monkeypatch.setattr(SpotGraphSimulationApplicationService, "tick", broken_tick)
        scenario = _small_scenario(tmp_path)

        result = run_random_agents(scenario, seed=0, max_world_ticks=6)

        exceptions = [f for f in result.findings if f.kind == "exception"]
        assert [(f.tick, f.detail.split(" [")[0]) for f in exceptions] == [(2, "RuntimeError: 仕込んだ例外")]
        assert result.reached_tick == 2
        report = result.report()
        assert report.startswith("FAIL persistent_world_demo seed=0 ticks=6 reached=2")
        assert "直前までの行動" in report
        assert result.actions and all(a.describe() in report for a in result.actions if a.tick <= 2)

    def test_world_tick_unit_failure_in_the_trace_is_reported_as_an_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """世界の tick が 1 体ぶんの例外を取りやめて trace に残し run を続けても、その tick の例外として出す。"""
        original = WorldRuntime.advance_tick

        def advance_tick_that_isolates_a_failure(self, *args, **kwargs):
            if self.current_tick() == 2:
                self._trace_recorder.record(
                    "world_tick_unit_failed", tick=2, stage="spot_graph", exception_type="RuntimeError"
                )
            return original(self, *args, **kwargs)

        monkeypatch.setattr(WorldRuntime, "advance_tick", advance_tick_that_isolates_a_failure)

        result = run_random_agents(_small_scenario(tmp_path), seed=0, max_world_ticks=6)

        exceptions = [f for f in result.findings if f.kind == "exception"]
        assert [f.tick for f in exceptions] == [2]
        assert "RuntimeError" in exceptions[0].detail
        assert result.reached_tick == 6

    @pytest.mark.parametrize(
        ("reason", "reported"),
        [("unexpected_error", True), ("memory_rule", True), ("contract_violation", True), ("unpaired_result", True), ("being_inner_record", False), ("empty_body", False)],
    )
    def test_broken_copy_to_the_being_short_term_memory_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str, reported: bool
    ) -> None:
        """Being 側の短期記憶へ写せなかった trace のうち、規則の崩れか想定外の例外だけを例外として出し、決めたとおりに写さないものは出さない (design_decisions D1824-7)。"""
        original = WorldRuntime.advance_tick

        def advance_tick_that_fails_a_copy(self, *args, **kwargs):
            if self.current_tick() == 2:
                self._trace_recorder.record(
                    "being_short_term_memory_not_copied", tick=2, being_id="being_w1_p1", source="observation", reason=reason, event_kind=None
                )
            return original(self, *args, **kwargs)

        monkeypatch.setattr(WorldRuntime, "advance_tick", advance_tick_that_fails_a_copy)

        result = run_random_agents(_small_scenario(tmp_path), seed=0, max_world_ticks=4)

        exceptions = [f for f in result.findings if f.kind == "exception"]
        assert [(f.tick, reason in f.detail) for f in exceptions] == ([(2, True)] if reported else [])

    def test_exception_swallowed_inside_a_tool_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """待つツールの中で想定外の例外が出てエージェントには伏せられても、待つたびに握られた例外として出す。"""

        def broken_wait(self, player_id, reason=""):
            raise RuntimeError("仕込んだ例外")

        monkeypatch.setattr(WorldRuntime, "do_wait", broken_wait)
        scenario = _small_scenario(tmp_path)

        result = run_random_agents(scenario, seed=0, max_world_ticks=20)

        waits = [a for a in result.actions if a.tool == "wait"]
        swallowed = [f for f in result.findings if f.kind == "swallowed_exception"]
        assert waits, "このシードでは一度も待たなかった。シードを変えないと何も確かめていない"
        assert len(swallowed) == len(waits)
        assert all(f.detail.startswith("wait: SYSTEM_ERROR") for f in swallowed)

    def test_an_action_whose_result_is_recorded_nowhere_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """待つ行動の結果だけ記録先に積まれないと、待つたびに 1 件出す。記録された他の行動は出さない。"""
        record = WorldRuntime._record_action_result

        def record_except_wait(self, player_id, action_summary, result_summary, *, tool_name, **kwargs):
            if tool_name != "wait":
                record(self, player_id, action_summary, result_summary, tool_name=tool_name, **kwargs)

        monkeypatch.setattr(WorldRuntime, "_record_action_result", record_except_wait)

        result = run_random_agents(_small_scenario(tmp_path), seed=0, max_world_ticks=20)

        waits = [a for a in result.actions if a.tool == "wait"]
        unrecorded = [f for f in result.findings if f.kind == "unrecorded_action"]
        assert waits, "このシードでは一度も待たなかった。シードを変えないと何も確かめていない"
        assert len(waits) < len(result.actions), "待つ以外の行動が無いと、誤って出さないことを確かめていない"
        assert len(unrecorded) == len(waits)
        assert all(f.detail.startswith("wait ") for f in unrecorded)


class TestDetectsLeaks:
    """内部の番号やシナリオの ID がエージェントへの文に出たら見つける。"""

    def test_internal_spot_number_in_a_description_is_reported_once(self, tmp_path: Path) -> None:
        """部屋の説明に「スポット 19」と書くと、毎ターン出ていても漏れは 1 件だけ、最初のターンの tick で出す。"""

        def leak(raw: dict[str, Any]) -> None:
            raw["spots"][0]["description"] = "石畳の小さな広場。看板に「スポット 19 → 16」と書いてある。"

        result = run_random_agents(_small_scenario(tmp_path, leak), seed=0, max_world_ticks=5)

        leaks = [f for f in result.findings if f.kind == "leak" and "スポット 19" in f.detail]
        assert [f.tick for f in leaks] == [1]

    def test_scenario_identifier_in_a_description_is_reported(self, tmp_path: Path) -> None:
        """部屋の説明にシナリオの接続 ID (plaza_to_garden) を書くと、漏れとして出す。"""

        def leak(raw: dict[str, Any]) -> None:
            raw["spots"][1]["description"] = "手入れされた庭。札に plaza_to_garden とある。"

        result = run_random_agents(_small_scenario(tmp_path, leak), seed=0, max_world_ticks=3)

        assert any("plaza_to_garden" in f.detail for f in result.findings if f.kind == "leak")

    @pytest.mark.parametrize(
        "line",
        [
            "到達不能: 16 → 19",
            "スポット 19 へは行けない",
            "spot_id=3 が見つからない",
            "今ターンは行動を控えた: tick=20",
            "メモ (追加: 2026-10-10 22:56)",
            "SpotId が不正",
        ],
    )
    def test_known_leak_shapes_are_found(self, line: str) -> None:
        """実 run や点検で見た漏れの形は、どれも漏れとして拾う。"""
        assert find_leaks(line, ()) == [line]

    @pytest.mark.parametrize(
        "line",
        [
            "現在時刻: Day 1 深夜 0:30",
            "[Day 1 10:00] → [Day 1 10:30]",
            "HP: 良好（100/100）",
            '- "北の坑道の水門" [水門を開ける → "open_gate_a"]',
            "メモを追加しました（ID: defb57…）",
        ],
    )
    def test_ordinary_prompt_lines_are_not_leaks(self, line: str) -> None:
        """時刻・体の数値・渡すための操作名・memo の印は、漏れとして拾わない。"""
        assert find_leaks(line, frozenset({"plaza_to_garden"})) == []


class TestToolDescriptions:
    """ツール定義の説明文も、エージェントが読む文として漏れを探す。"""

    def test_descriptions_and_enum_values_of_nested_properties_are_collected(self) -> None:
        """ツールと引数の説明文、enum の値を集め、その中の「スポット 19」を漏れとして拾える。"""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "travel_to",
                    "description": "移動する。",
                    "parameters": {
                        "properties": {
                            "destination_label": {"type": "string", "description": "行き先 (例: スポット 19)"},
                            "speed": {"type": "string", "enum": ["walk", "run"]},
                        }
                    },
                },
            }
        ]

        texts = tool_texts(tools)

        assert texts == ["移動する。", "行き先 (例: スポット 19)", "walk run"]
        assert find_leaks(texts[1], ()) == ["行き先 (例: スポット 19)"]

    def test_a_leak_in_a_presented_tool_description_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """エージェントに渡したツールの説明文に「スポット 99」があると、本文に無くても漏れとして出す。"""
        import scripts.fuzz_scenario_with_random_agents as fuzz

        monkeypatch.setattr(fuzz, "tool_texts", lambda tools: ["説明: スポット 99 へ行ける"])

        result = run_random_agents(_small_scenario(tmp_path), seed=0, max_world_ticks=2)

        assert any(f.kind == "leak" and f.detail == "説明: スポット 99 へ行ける" for f in result.findings)


class TestScenarioChecks:
    """シナリオごとの検査を足せる。"""

    def test_extra_check_findings_are_reported_with_the_tick(self, tmp_path: Path) -> None:
        """足した検査が文を返すと、ターンごとに、その tick の check として出す。"""

        def no_traveler_named_before_meeting(view: TurnView) -> list[str]:
            return ["旅人の名前が会う前に出た"] if any("旅人" in t for t in view.texts) else []

        result = run_random_agents(
            _small_scenario(tmp_path), seed=0, max_world_ticks=2, extra_checks=[no_traveler_named_before_meeting]
        )

        checks = [f for f in result.findings if f.kind == "check"]
        assert checks[0] == FuzzFinding("check", 1, "旅人の名前が会う前に出た")
        assert {f.tick for f in checks} == {1, 2}


class TestSummary:
    """複数シードの結果を、穴の形ごとにまとめる。"""

    def test_same_shape_from_different_seeds_is_one_line_with_the_earliest_seed(self) -> None:
        """数字だけ違う同じ漏れが 2 つのシードで出たら 1 行にまとめ、最も早い tick のシードを示す。"""
        results = [
            FuzzResult("s", 1, 10, findings=[FuzzFinding("leak", 5, "待った: tick=5")]),
            FuzzResult("s", 2, 10, findings=[FuzzFinding("leak", 3, "待った: tick=3")]),
            FuzzResult("s", 3, 10),
        ]

        text = summarize(results)

        assert text.splitlines() == [
            "== 3 run(s), 2 failed, 1 distinct finding(s)",
            "s [leak] seeds=2 (first: seed 2 tick 3) 待った: tick=N",
        ]


class TestMineVillage:
    """廃坑の山村を、でたらめな行動で決めた tick まで回せる。"""

    @pytest.mark.parametrize("seed", [0, 1])
    def test_all_four_act_and_touch_the_world(self, seed: int) -> None:
        """10 tick 回すと、4 人とも行動し、移動とものへの働きかけの両方が起き、run が例外で止まらない。"""
        result = run_random_agents(_MINE, seed=seed, max_world_ticks=10)

        assert "exception" not in _kinds(result)
        assert result.reached_tick == 10
        assert {a.player_id for a in result.actions} == {1, 2, 3, 4}
        assert {"travel_to", "interact"} <= {a.tool for a in result.actions}


class TestDetectsLoggedErrors:
    """engine が ERROR のログを出したら見つける。"""

    def test_error_log_is_reported_even_when_the_root_logger_is_silenced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """root の level を CRITICAL に絞っていても、待つたびに出した ERROR ログを logged_error として出す。"""
        import logging

        def wait_with_error_log(self, player_id, reason=""):
            logging.getLogger("ai_rpg_world.test_fuzz").error("仕込んだエラー")
            return 0

        monkeypatch.setattr(WorldRuntime, "do_wait", wait_with_error_log)
        monkeypatch.setattr(logging.getLogger(), "level", logging.CRITICAL)
        scenario = _small_scenario(tmp_path)

        result = run_random_agents(scenario, seed=0, max_world_ticks=20)

        waits = [a for a in result.actions if a.tool == "wait"]
        logged = [f for f in result.findings if f.kind == "logged_error"]
        assert waits, "このシードでは一度も待たなかった。シードを変えないと何も確かめていない"
        assert len(logged) == len(waits)
        assert all(f.detail == "ai_rpg_world.test_fuzz: 仕込んだエラー" for f in logged)


_PLANTED_HOLE = KnownHole(9001, "leak", re.compile(r"看板に「スポット 19」"))


def _plant_spot_number(raw: dict[str, Any]) -> None:
    raw["spots"][0]["description"] = "石畳の小さな広場。看板に「スポット 19」と書いてある。"


class TestKnownHoles:
    """Issue にした穴は、見つけても run を失敗にせず、Issue 番号を添えて出す。"""

    def test_a_known_leak_is_tagged_with_its_issue_and_does_not_fail_the_run(self) -> None:
        """既知の穴の形に合う漏れだけなら、OK の行にその Issue 番号を添える。"""
        finding = classify(FuzzFinding("leak", 3, "広場。看板に「スポット 19」と書いてある。"), [_PLANTED_HOLE])
        result = FuzzResult("s", 1, 10, reached_tick=10, findings=[finding])

        assert finding.known_issue == 9001
        assert not result.failed
        assert result.report() == "OK   s seed=1 ticks=10 reached=10 actions=0 known=#9001"

    def test_an_unknown_leak_beside_a_known_one_still_fails_the_run(self) -> None:
        """既知の穴と一緒に新しい漏れが出たら失敗にし、新しい漏れだけを並べる。"""
        findings = [
            classify(FuzzFinding("leak", 2, "看板に「スポット 19」"), [_PLANTED_HOLE]),
            classify(FuzzFinding("leak", 4, "到達不能: 16 → 19"), [_PLANTED_HOLE]),
        ]
        result = FuzzResult("s", 1, 10, reached_tick=10, findings=findings)

        assert result.failed
        assert result.report().splitlines()[:2] == [
            "FAIL s seed=1 ticks=10 reached=10 actions=0 known=#9001",
            "  [leak] tick 4: 到達不能: 16 → 19",
        ]

    def test_known_shape_of_another_kind_is_not_excused(self) -> None:
        """既知の穴は種類まで合わせる。同じ形が例外の文に出ても、既知の漏れとしては扱わない。"""
        finding = classify(FuzzFinding("exception", 3, "RuntimeError: 看板に「スポット 19」"), [_PLANTED_HOLE])

        assert finding.known_issue is None

    def test_run_tags_leaks_matching_the_given_known_holes(self, tmp_path: Path) -> None:
        """渡した既知の穴に合う漏れは、run の中でもその Issue 番号の印付きで出て、run を失敗にしない。"""
        result = run_random_agents(
            _small_scenario(tmp_path, _plant_spot_number), seed=0, max_world_ticks=3, known_holes=[_PLANTED_HOLE]
        )

        planted = [f for f in result.findings if "スポット 19" in f.detail]
        assert planted
        assert {f.known_issue for f in planted} == {9001}
        assert not result.failed

    def test_passing_no_known_holes_reports_every_finding(self, tmp_path: Path) -> None:
        """既知の穴を空にして回すと、同じ漏れが失敗として出る。"""
        result = run_random_agents(
            _small_scenario(tmp_path, _plant_spot_number), seed=0, max_world_ticks=3, known_holes=()
        )

        assert any("スポット 19" in f.detail and f.known_issue is None for f in result.findings)
        assert result.failed


class TestFixedHolesStayFixed:
    """直して KNOWN_HOLES から外した穴が、でたらめに動かしても再び出ないことを見張る。"""

    def test_wait_result_does_not_leak_world_tick(self, tmp_path: Path) -> None:
        """待つを何度も選ぶシードで回しても、待つの結果に tick の番号が出ない (#1562)。"""
        result = run_random_agents(_small_scenario(tmp_path), seed=0, max_world_ticks=20, known_holes=())

        assert [a for a in result.actions if a.tool == "wait"], "このシードでは一度も待たなかった。シードを変えないと何も確かめていない"
        assert [f for f in result.findings if f.kind == "leak"] == []


class TestUnreadableCandidates:
    """スタブが読み戻せない候補表の行を見つける。"""

    def test_rows_after_a_malformed_row_are_reported(self) -> None:
        """表の途中に読めない行があると、その行から後ろを読めなかった行として返す。"""
        text = "\n".join([
            "【現在選べる対象引数】",
            '- travel_to.destination_label: "集会所"',
            "- interact.target_label: 金庫",
            '- use_item.item_label: "カンテラ"',
            "※ 一覧にあることは操作の成功を保証しない。",
        ])

        assert unreadable_candidate_lines(text) == ["- interact.target_label: 金庫", '- use_item.item_label: "カンテラ"']

    def test_a_well_formed_table_has_no_unreadable_rows(self) -> None:
        """正しく描いた表なら、読めなかった行は無い。"""
        text = '【現在選べる対象引数】\n- travel_to.destination_label: "集会所", "倉庫"\n※ 注記'

        assert unreadable_candidate_lines(text) == []

"""scripts/build_trace_viewer.py の単体テスト (Issue #188 Phase 1d β)。

vendor 取得 (Cytoscape.js download) は ``unittest.mock`` で偽装し、
ネットワーク無しで動かす。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import JsonlTraceRecorder

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.build_trace_viewer import (  # noqa: E402
    _format_event_body,
    build_memo_state_timeline,
    build_position_timeline,
    collect_players,
    compute_event_heatmap,
    compute_trace_moments,
    group_events_by_tick,
    load_scenario_topology,
    render_viewer_html,
)
from scripts._viewer_vendor import VendorAsset  # noqa: E402


def _fake_asset() -> VendorAsset:
    """テスト用にダミー Cytoscape JS を返す。"""
    return VendorAsset(
        name="cytoscape",
        version="0.0.0-test",
        content="/* fake cytoscape */ var cytoscape = function() {};",
        sha256="0" * 64,
    )


def _sample_events() -> list[TraceEvent]:
    return [
        TraceEvent(
            seq=1,
            timestamp="t",
            kind=TraceEventKind.RUN_START,
            payload={"scenario": "demo"},
        ),
        TraceEvent(
            seq=2,
            timestamp="t",
            kind=TraceEventKind.POSITION_CHANGE,
            tick=0,
            player_id=1,
            payload={
                "from_spot_id": None,
                "to_spot_id": "s1",
                "spot_name": "制御室",
                "player_name": "カイト",
            },
        ),
        TraceEvent(
            seq=3,
            timestamp="t",
            kind=TraceEventKind.POSITION_CHANGE,
            tick=0,
            player_id=2,
            payload={
                "from_spot_id": None,
                "to_spot_id": "s2",
                "spot_name": "廊下",
                "player_name": "リン",
            },
        ),
        TraceEvent(
            seq=4,
            timestamp="t",
            kind=TraceEventKind.ACTION,
            tick=1,
            player_id=1,
            payload={"tool": "examine", "arguments": {"target": "panel"}},
        ),
        TraceEvent(
            seq=5,
            timestamp="t",
            kind=TraceEventKind.ACTION_RESULT,
            tick=1,
            player_id=1,
            payload={"success": True, "result_summary": "ok"},
        ),
        TraceEvent(
            seq=6,
            timestamp="t",
            kind=TraceEventKind.POSITION_CHANGE,
            tick=2,
            player_id=2,
            payload={
                "from_spot_id": "s2",
                "to_spot_id": "s3",
                "spot_name": "金庫室",
            },
        ),
        TraceEvent(
            seq=7,
            timestamp="t",
            kind=TraceEventKind.RUN_END,
            payload={"outcome": "WIN", "last_tick": 2},
        ),
    ]


class TestLoadScenarioTopology:
    """scenario.json からの spot graph 抽出。"""

    def test_存在しない_scenario_は_空のトポロジを返す(self, tmp_path: Path) -> None:
        """ファイルがないときも crash せず空で返す。"""
        topo = load_scenario_topology(tmp_path / "missing.json")
        assert topo == {"spots": [], "connections": []}

    def test_標準的な_spot_graph_を抽出できる(self, tmp_path: Path) -> None:
        """spot_graph.spots と spot_graph.connections を読む。"""
        scen = tmp_path / "s.json"
        scen.write_text(
            json.dumps(
                {
                    "spot_graph": {
                        "spots": [
                            {"id": "a", "name": "A 部屋"},
                            {"id": "b", "name": "B 部屋"},
                        ],
                        "connections": [
                            {
                                "from_spot_id": "a",
                                "to_spot_id": "b",
                                "is_bidirectional": True,
                            }
                        ],
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        topo = load_scenario_topology(scen)
        assert len(topo["spots"]) == 2
        assert topo["spots"][0]["name"] == "A 部屋"
        assert topo["connections"][0]["from"] == "a"
        assert topo["connections"][0]["bidirectional"] is True

    def test_壊れた_JSON_でも_空のトポロジを返す(self, tmp_path: Path) -> None:
        """parse 失敗時もクラッシュせず空で返す。"""
        scen = tmp_path / "broken.json"
        scen.write_text("{not json", encoding="utf-8")
        topo = load_scenario_topology(scen)
        assert topo == {"spots": [], "connections": []}


class TestCollectPlayers:
    """trace から登場プレイヤー一覧を抽出。"""

    def test_最終位置を_position_change_の最後で決定する(self) -> None:
        """同じプレイヤーが複数回移動した場合、最後の to_spot_id が final になる。"""
        players = collect_players(_sample_events())
        # カイト (id=1) は s1 のまま、リン (id=2) は s2 → s3 で final=s3
        by_id = {p["id"]: p for p in players}
        assert by_id[1]["final_spot_id"] == "s1"
        assert by_id[2]["final_spot_id"] == "s3"

    def test_player_name_は_payload_から_拾われる(self) -> None:
        """payload.player_name があれば名前として使う。"""
        players = collect_players(_sample_events())
        by_id = {p["id"]: p for p in players}
        assert by_id[1]["name"] == "カイト"
        assert by_id[2]["name"] == "リン"

    def test_player_id_順に_ソートされる(self) -> None:
        """出力順は id 昇順 (UI 安定性のため)。"""
        players = collect_players(_sample_events())
        assert [p["id"] for p in players] == [1, 2]

    def test_spot_name_to_id_で_trace_と_scenario_の_id_差分を吸収する(self) -> None:
        """trace の to_spot_id="1" と scenario の id="control_room" を spot_name "制御室" 経由で結びつける。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.POSITION_CHANGE,
                tick=0,
                player_id=1,
                payload={
                    "from_spot_id": None,
                    "to_spot_id": "1",  # runtime の内部数値 id
                    "spot_name": "制御室",
                    "player_name": "カイト",
                },
            )
        ]
        name_to_id = {"制御室": "control_room"}
        players = collect_players(events, spot_name_to_id=name_to_id)
        assert players[0]["final_spot_id"] == "control_room"
        assert players[0]["final_spot_name"] == "制御室"


class TestGroupEventsByTick:
    """tick 別 grouping。"""

    def test_tick_None_は_別グループとして扱われる(self) -> None:
        """run_start (tick=None) と tick=0 以降は分かれる。"""
        grouped = group_events_by_tick(_sample_events())
        assert None in grouped
        assert 0 in grouped
        assert 1 in grouped


class TestFormatEventBody:
    """個別 event の 1 行サマリ HTML。"""

    def test_action_は_tool_名を含む(self) -> None:
        e = _sample_events()[3]
        out = _format_event_body(e)
        assert "examine" in out
        assert "panel" in out

    def test_action_result_失敗は_NG_マーク(self) -> None:
        e = TraceEvent(
            seq=1,
            timestamp="t",
            kind=TraceEventKind.ACTION_RESULT,
            tick=1,
            player_id=1,
            payload={"success": False, "result_summary": "broke"},
        )
        out = _format_event_body(e)
        assert "[NG]" in out
        assert "broke" in out

    def test_position_change_初期配置は_spawn_と表示(self) -> None:
        e = _sample_events()[1]  # カイト初期配置
        out = _format_event_body(e)
        assert "spawn" in out
        assert "制御室" in out

    def test_position_change_移動は_矢印で_from_to(self) -> None:
        e = _sample_events()[5]  # リン s2 → s3
        out = _format_event_body(e)
        assert "→" in out
        assert "金庫室" in out


class TestRenderViewerHtml:
    """end-to-end の HTML 出力。"""

    def test_HTML_に_必須要素が含まれる(self) -> None:
        """ヘッダ / map 用 #cy / event log / Cytoscape script。"""
        topo = {
            "spots": [{"id": "s1", "name": "制御室"}, {"id": "s2", "name": "廊下"}, {"id": "s3", "name": "金庫室"}],
            "connections": [
                {"from": "s1", "to": "s2", "bidirectional": True},
                {"from": "s2", "to": "s3", "bidirectional": True},
            ],
        }
        out = render_viewer_html(
            title="test-run",
            events=_sample_events(),
            scenario_topology=topo,
            cytoscape_js_src="/* fake */",
        )
        assert "<title>test-run" in out
        assert 'id="cy"' in out
        assert "event-log" in out
        assert "fake" in out  # Cytoscape script inlined
        # player 名と最終位置が出る
        assert "カイト" in out
        assert "リン" in out
        # 全角化なしで日本語の spot 名も出る
        assert "制御室" in out

    def test_scenario_が空でも_HTML_は生成できる(self) -> None:
        """topology 空でも HTML は生成される (map が空表示になるだけ)。"""
        out = render_viewer_html(
            title="no-scenario",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert 'id="cy"' in out

    def test_outcome_は_run_end_payload_から取られる(self) -> None:
        """RUN_END の payload.outcome が header に出る。"""
        out = render_viewer_html(
            title="x",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert "WIN" in out


class TestMainCli:
    """``main()`` の CLI 動作 (vendor download は mock)。"""

    def test_run_dir_から_viewer_html_を生成する(self, tmp_path: Path) -> None:
        """trace.jsonl + scenario.json から viewer.html を出力。"""
        from scripts import build_trace_viewer  # noqa: WPS433

        # 入力作成
        with JsonlTraceRecorder(tmp_path / "trace.jsonl") as rec:
            rec.record(TraceEventKind.RUN_START)
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=0,
                player_id=1,
                from_spot_id=None,
                to_spot_id="s1",
                spot_name="A",
                player_name="P1",
            )
            rec.record(TraceEventKind.RUN_END, outcome="WIN")
        (tmp_path / "scenario.json").write_text(
            json.dumps(
                {
                    "spot_graph": {
                        "spots": [{"id": "s1", "name": "A"}],
                        "connections": [],
                    }
                }
            ),
            encoding="utf-8",
        )

        with patch.object(
            build_trace_viewer, "fetch_cytoscape", return_value=_fake_asset()
        ):
            rc = build_trace_viewer.main([str(tmp_path)])

        assert rc == 0
        out = tmp_path / "viewer.html"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "P1" in content
        assert 'id="cy"' in content

    def test_trace_jsonl_が無いと_エラー(self, tmp_path: Path) -> None:
        """trace.jsonl 未配置なら argparse のエラーで終わる (SystemExit)。"""
        from scripts import build_trace_viewer  # noqa: WPS433

        try:
            build_trace_viewer.main([str(tmp_path)])
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError("expected SystemExit for missing trace.jsonl")


class TestPositionTimeline:
    """build_position_timeline の挙動 (PR γ playback の入力)。"""

    def test_各_tick_でのスナップショットを返す(self) -> None:
        """各 position_change tick のスナップショットが順に積まれる。"""
        events = _sample_events()
        timeline = build_position_timeline(
            events, spot_name_to_id={"制御室": "s1", "廊下": "s2", "金庫室": "s3"}
        )
        # tick 0: カイト=s1, リン=s2 (初期配置)
        assert timeline[0] == {1: "s1", 2: "s2"}
        # tick 2: リンが移動 → カイトはまだ s1, リン=s3
        assert timeline[2] == {1: "s1", 2: "s3"}

    def test_position_change_の無い_tick_はスナップショット未登録(self) -> None:
        """変化が無い tick はキーが入らない (JS 側で前進補間する想定)。"""
        events = _sample_events()
        timeline = build_position_timeline(events)
        # tick 1 は position_change なし (action のみ)
        assert 1 not in timeline


class TestMemoStateTimeline:
    """build_memo_state_timeline の挙動 (PR γ memo panel 用)。"""

    def test_memo_add_で_active_な_memo_が記録される(self) -> None:
        """memo_add 発生 tick のスナップショットに該当 memo が active で含まれる。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.MEMO_ADD,
                tick=3,
                player_id=1,
                payload={"memo_id": "m1", "content": "扉を固定"},
            ),
        ]
        timeline = build_memo_state_timeline(events)
        snap = timeline[3]
        assert len(snap) == 1
        assert snap[0]["memo_id"] == "m1"
        assert snap[0]["status"] == "active"
        assert snap[0]["added_tick"] == 3

    def test_memo_done_で_status_が_done_になる(self) -> None:
        """memo_done 後のスナップショットで該当 memo の status=done。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.MEMO_ADD,
                tick=3,
                player_id=1,
                payload={"memo_id": "m1", "content": "x"},
            ),
            TraceEvent(
                seq=2,
                timestamp="t",
                kind=TraceEventKind.MEMO_DONE,
                tick=10,
                player_id=1,
                payload={"memo_id": "m1"},
            ),
        ]
        timeline = build_memo_state_timeline(events)
        # tick 3 の時点では active
        assert timeline[3][0]["status"] == "active"
        # tick 10 で done
        done = timeline[10][0]
        assert done["status"] == "done"
        assert done["done_tick"] == 10


class TestEventHeatmap:
    """compute_event_heatmap の出力。"""

    def test_kind_別に_tick_配列を返す(self) -> None:
        """action / observation / memo / position_change それぞれの tick 配列が揃う。"""
        events = _sample_events()
        hm = compute_event_heatmap(events)
        assert "ticks" in hm and "action" in hm and "memo" in hm
        # tick 1 に action が 1 件あった
        assert hm["action"][1] >= 1
        # 全配列長は ticks と同じ
        n = len(hm["ticks"])
        assert all(len(hm[k]) == n for k in ("action", "observation", "memo", "position_change"))


class TestComputeTraceMoments:
    """compute_trace_moments (PR ε): trace navigator の自動ブックマーク抽出。"""

    def test_run_start_と_run_end_を_start_end_kind_で_抽出する(self) -> None:
        """RUN_START → kind="start", RUN_END → kind="end" (label=outcome)。"""
        events = _sample_events()
        moments = compute_trace_moments(events)
        kinds = [m["kind"] for m in moments]
        assert "start" in kinds
        assert "end" in kinds
        end_m = next(m for m in moments if m["kind"] == "end")
        assert end_m["label"] == "WIN"

    def test_memo_add_は_memo_kind_で_score_中(self) -> None:
        """memo_add は kind="memo", score≈65, content が detail に入る。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.MEMO_ADD,
                tick=3,
                player_id=1,
                payload={"memo_id": "m1", "content": "power_on を維持"},
            ),
        ]
        moments = compute_trace_moments(events)
        assert len(moments) == 1
        assert moments[0]["kind"] == "memo"
        assert moments[0]["detail"] == "power_on を維持"
        assert moments[0]["score"] == 65

    def test_failed_action_result_は_failed_kind_で_score_高(self) -> None:
        """action_result.success=False は kind="failed" (score=85)。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.ACTION_RESULT,
                tick=5,
                player_id=2,
                payload={"success": False, "result_summary": "電力不足"},
            ),
        ]
        moments = compute_trace_moments(events)
        assert len(moments) == 1
        assert moments[0]["kind"] == "failed"
        assert moments[0]["score"] == 85

    def test_position_change_の初期配置は_moment_に含めない(self) -> None:
        """from_spot_id=None は除外、実 move のみ kind="move" として拾う。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.POSITION_CHANGE,
                tick=0,
                player_id=1,
                payload={"from_spot_id": None, "to_spot_id": "a", "spot_name": "制御室"},
            ),
            TraceEvent(
                seq=2,
                timestamp="t",
                kind=TraceEventKind.POSITION_CHANGE,
                tick=2,
                player_id=1,
                payload={"from_spot_id": "a", "to_spot_id": "b", "spot_name": "金庫室"},
            ),
        ]
        moments = compute_trace_moments(events)
        # 初期配置は moment に含めない
        assert len(moments) == 1
        assert moments[0]["kind"] == "move"
        assert "金庫室" in moments[0]["label"]

    def test_成功_action_result_で_キーワード含むなら_result_kind_で拾う(self) -> None:
        """result_summary に "=true" / "OPEN" / "latch" 等の状態変化語が含まれれば kind="result"。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="t",
                kind=TraceEventKind.ACTION_RESULT,
                tick=4,
                player_id=1,
                payload={"success": True, "result_summary": "power_on=true / 金庫扉=OPEN"},
            ),
            TraceEvent(
                seq=2,
                timestamp="t",
                kind=TraceEventKind.ACTION_RESULT,
                tick=5,
                player_id=1,
                payload={"success": True, "result_summary": "見た目を確認した"},  # キーワード無し
            ),
        ]
        moments = compute_trace_moments(events)
        assert len(moments) == 1
        assert moments[0]["kind"] == "result"


class TestTacticalThemeMarkers:
    """PR ε: viewer HTML が tactical 風テーマの要素を含む回帰防止。"""

    def test_HTML_に_tactical_テーマ要素が含まれる(self) -> None:
        out = render_viewer_html(
            title="t",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        # 設計トークン
        assert "--bg:" in out
        assert "--gold:" in out
        # 新セクション
        assert 'id="trace-nav-section"' in out
        assert 'id="moment-rail"' in out
        # 新ラベル
        assert "Tactical map" in out
        assert "Trace navigator" in out
        assert "Objectives / Active memo" in out
        # badge outcome chip
        assert "badge outcome" in out
        # moment_rail へのデータ inline (合成 trace なので start + end は最低含まれる)
        assert "traceMoments" in out

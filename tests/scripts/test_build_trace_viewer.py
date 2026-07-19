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
    build_speech_timeline,
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

    def test_returns_empty_scenario(self, tmp_path: Path) -> None:
        """ファイルがないときも crash せず空で返す。"""
        topo = load_scenario_topology(tmp_path / "missing.json")
        assert topo == {"spots": [], "connections": []}

    def test_spot_graph(self, tmp_path: Path) -> None:
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

    def test_returns_empty_json(self, tmp_path: Path) -> None:
        """parse 失敗時もクラッシュせず空で返す。"""
        scen = tmp_path / "broken.json"
        scen.write_text("{not json", encoding="utf-8")
        topo = load_scenario_topology(scen)
        assert topo == {"spots": [], "connections": []}


class TestCollectPlayers:
    """trace から登場プレイヤー一覧を抽出。"""

    def test_position_change_last(self) -> None:
        """同じプレイヤーが複数回移動した場合、最後の to_spot_id が final になる。"""
        players = collect_players(_sample_events())
        # カイト (id=1) は s1 のまま、リン (id=2) は s2 → s3 で final=s3
        by_id = {p["id"]: p for p in players}
        assert by_id[1]["final_spot_id"] == "s1"
        assert by_id[2]["final_spot_id"] == "s3"

    def test_player_name_payload_picked_up(self) -> None:
        """payload.player_name があれば名前として使う。"""
        players = collect_players(_sample_events())
        by_id = {p["id"]: p for p in players}
        assert by_id[1]["name"] == "カイト"
        assert by_id[2]["name"] == "リン"

    def test_player_id_sorted(self) -> None:
        """出力順は id 昇順 (UI 安定性のため)。"""
        players = collect_players(_sample_events())
        assert [p["id"] for p in players] == [1, 2]

    def test_spot_name_id_trace_scenario_id(self) -> None:
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

    def test_tick_none_different(self) -> None:
        """run_start (tick=None) と tick=0 以降は分かれる。"""
        grouped = group_events_by_tick(_sample_events())
        assert None in grouped
        assert 0 in grouped
        assert 1 in grouped

    def test_llm_call_prompt_section_breakdown_excluded(self) -> None:
        """実験 #26 user feedback: 性能計測系 kind は timeline から非表示。"""
        events = [
            TraceEvent(seq=1, timestamp="t", kind="action", tick=0, player_id=1, payload={"tool": "x"}),
            TraceEvent(seq=2, timestamp="t", kind="llm_call", tick=0, player_id=1, payload={"model": "m"}),
            TraceEvent(seq=3, timestamp="t", kind="prompt_section_breakdown", tick=0, player_id=1, payload={}),
            TraceEvent(seq=4, timestamp="t", kind="observation", tick=0, player_id=2, payload={"prose": "hi"}),
        ]
        grouped = group_events_by_tick(events)
        kinds_at_0 = [e.kind for e in grouped[0]]
        assert "action" in kinds_at_0
        assert "observation" in kinds_at_0
        assert "llm_call" not in kinds_at_0
        assert "prompt_section_breakdown" not in kinds_at_0

    def test_hide_metrics_kinds_false_can_display(self) -> None:
        """hidemetricskindsFalse で表示できる。"""
        events = [
            TraceEvent(seq=1, timestamp="t", kind="llm_call", tick=0, player_id=1, payload={}),
        ]
        grouped = group_events_by_tick(events, hide_metrics_kinds=False)
        assert any(e.kind == "llm_call" for e in grouped[0])

    def test_duplicate_observation_excluded(self) -> None:
        """同 tick / 同 prose / 同 structured.type の observation は 1 件に。
        (4 player broadcast で同じ prose が 4 連続並ぶのを抑制)"""
        events = [
            TraceEvent(seq=i, timestamp="t", kind="observation", tick=0, player_id=i,
                       payload={"prose": "雨が降ってきた", "structured": {"type": "weather_changed"}})
            for i in range(1, 5)
        ]
        grouped = group_events_by_tick(events)
        obs = [e for e in grouped[0] if e.kind == "observation"]
        assert len(obs) == 1, f"重複除外後は 1 件のはずが {len(obs)} 件"

    def test_different_prose_observation_remains(self) -> None:
        """prose が違えば別 event として両方残す。"""
        events = [
            TraceEvent(seq=1, timestamp="t", kind="observation", tick=0, player_id=1,
                       payload={"prose": "A が起きた", "structured": {"type": "x"}}),
            TraceEvent(seq=2, timestamp="t", kind="observation", tick=0, player_id=2,
                       payload={"prose": "B が起きた", "structured": {"type": "x"}}),
        ]
        grouped = group_events_by_tick(events)
        obs = [e for e in grouped[0] if e.kind == "observation"]
        assert len(obs) == 2


class TestFormatEventBody:
    """個別 event の 1 行サマリ HTML。"""

    def test_includes_action_tool(self) -> None:
        """action は tool 名を含む。"""
        e = _sample_events()[3]
        out = _format_event_body(e)
        assert "examine" in out
        assert "panel" in out

    def test_action_result_failure_ng(self) -> None:
        """action result 失敗は NG マーク。"""
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

    def test_position_change_initial_position_spawn(self) -> None:
        """position change 初期配置は spawn と表示。"""
        e = _sample_events()[1]  # カイト初期配置
        out = _format_event_body(e)
        assert "spawn" in out
        assert "制御室" in out

    def test_position_change(self) -> None:
        """position change 移動は 矢印で from to。"""
        e = _sample_events()[5]  # リン s2 → s3
        out = _format_event_body(e)
        assert "→" in out
        assert "金庫室" in out


class TestRenderViewerHtml:
    """end-to-end の HTML 出力。"""

    def test_html_element_included(self) -> None:
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

    def test_scenario_empty_html_can_create(self) -> None:
        """topology 空でも HTML は生成される (map が空表示になるだけ)。"""
        out = render_viewer_html(
            title="no-scenario",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert 'id="cy"' in out

    def test_outcome_run_end_payload(self) -> None:
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

    def test_run_dir_viewer_html(self, tmp_path: Path) -> None:
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

    def test_trace_jsonl_error(self, tmp_path: Path) -> None:
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

    def test_returns_tick(self) -> None:
        """各 position_change tick のスナップショットが順に積まれる。"""
        events = _sample_events()
        timeline = build_position_timeline(
            events, spot_name_to_id={"制御室": "s1", "廊下": "s2", "金庫室": "s3"}
        )
        # tick 0: カイト=s1, リン=s2 (初期配置)
        assert timeline[0] == {1: "s1", 2: "s2"}
        # tick 2: リンが移動 → カイトはまだ s1, リン=s3
        assert timeline[2] == {1: "s1", 2: "s3"}

    def test_position_change_tick_unregistered(self) -> None:
        """変化が無い tick はキーが入らない (JS 側で前進補間する想定)。"""
        events = _sample_events()
        timeline = build_position_timeline(events)
        # tick 1 は position_change なし (action のみ)
        assert 1 not in timeline


class TestMemoStateTimeline:
    """build_memo_state_timeline の挙動 (PR γ memo panel 用)。"""

    def test_memo_add_active_memo_recorded(self) -> None:
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

    def test_memo_done_status_done(self) -> None:
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

    def test_returns_kind_tick_column(self) -> None:
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

    def test_run_start_run_end_start_end_kind(self) -> None:
        """RUN_START と RUN_END は開始・終了の moment として扱われる。"""
        events = _sample_events()
        moments = compute_trace_moments(events)
        kinds = [m["kind"] for m in moments]
        assert "start" in kinds
        assert "end" in kinds
        end_m = next(m for m in moments if m["kind"] == "end")
        assert end_m["label"] == "WIN"

    def test_memo_add_has_medium_score_from_memo_kind(self) -> None:
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

    def test_failed_action_result_has_high_score_from_failed_kind(self) -> None:
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

    def test_excludes_position_change_initial_position_moment(self) -> None:
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

    def test_includes_result_kind_finds_success_action_result_key(self) -> None:
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

    def test_html_tactical_element_included(self) -> None:
        """HTML に tactical テーマ要素が含まれる。"""
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


class TestSpeechTimeline:
    """build_speech_timeline (PR η): speech / inner_thought の tick 別 bubble。"""

    def _evt(self, seq, tick, pid, tool, args):
        return TraceEvent(
            seq=seq,
            timestamp="t",
            kind=TraceEventKind.ACTION,
            tick=tick,
            player_id=pid,
            payload={"tool": tool, "arguments": args},
        )

    def test_speech_say_is_found_by_speech_kind(self) -> None:
        """``say`` / ``speech_*`` ツールの message を kind="speech" として拾う。"""
        events = [self._evt(1, 3, 1, "say", {"message": "hello"})]
        tl = build_speech_timeline(events)
        assert tl[3][0]["kind"] == "speech"
        assert tl[3][0]["text"] == "hello"
        assert tl[3][0]["player_id"] == 1

    def test_finds_inner_thought_kind_thought(self) -> None:
        """arguments.inner_thought は kind="thought" として別ものとして拾う。"""
        events = [
            self._evt(1, 5, 1, "examine", {"target": "x", "inner_thought": "考えごと"})
        ]
        tl = build_speech_timeline(events)
        # speech は無く thought のみ
        kinds = [b["kind"] for b in tl[5]]
        assert "thought" in kinds
        assert "speech" not in kinds

    def test_finds_say_inner_thought_action(self) -> None:
        """同一 action に message と inner_thought 両方あれば bubble 2 件。"""
        events = [
            self._evt(1, 3, 1, "speech_say", {"message": "公開", "inner_thought": "心声"})
        ]
        tl = build_speech_timeline(events)
        kinds = sorted([b["kind"] for b in tl[3]])
        assert kinds == ["speech", "thought"]

    def test_bubble_default_one_tick_displayed(self) -> None:
        """実験 #26 user feedback: 当該 tick だけに留めて次 tick には残さない。
        OFF / ON_FULL の trace で「次 tick まで残る」のが視認上の重なりの
        原因だったため persistence default を 2 → 1 に変更。"""
        events = [self._evt(1, 3, 1, "say", {"message": "hi"})]
        tl = build_speech_timeline(events)
        assert 3 in tl
        assert 4 not in tl  # persistence=1 で発生 tick のみ

    def test_persistence(self) -> None:
        """テスト目的や旧挙動互換が必要なら kwarg で長くも設定可能。"""
        events = [self._evt(1, 3, 1, "say", {"message": "hi"})]
        tl = build_speech_timeline(events, bubble_persistence=3)
        assert 3 in tl and 4 in tl and 5 in tl
        assert 6 not in tl

    def test_player_kind_before_overwrites(self) -> None:
        """同じ player の連続発言は前の bubble を即上書き (overlap しない)。"""
        events = [
            self._evt(1, 3, 1, "say", {"message": "first"}),
            self._evt(2, 4, 1, "say", {"message": "second"}),
        ]
        tl = build_speech_timeline(events)
        # tick 3 は first だけ
        assert [b["text"] for b in tl[3]] == ["first"]
        # tick 4 は second だけ (first は次発言で打ち切り)
        assert [b["text"] for b in tl[4]] == ["second"]

    def test_inner_thought_truncate(self) -> None:
        """100 字を超える inner_thought は "…" で切り詰める。"""
        long_text = "あ" * 200
        events = [self._evt(1, 1, 1, "examine", {"inner_thought": long_text})]
        tl = build_speech_timeline(events, max_chars=100)
        text = tl[1][0]["text"]
        assert len(text) <= 100
        assert text.endswith("…")

    def test_non_speech_inner_thought_timeline(self) -> None:
        """普通の action は bubble 化されない (map をうるさくしない)。"""
        events = [self._evt(1, 3, 1, "examine", {"target": "panel"})]
        tl = build_speech_timeline(events)
        assert tl == {}


class TestRenderViewerHtmlSpeech:
    """render_viewer_html が speech bubble UI を埋め込むか確認。"""

    def test_html_speech_timeline_toggle_thoughts_bubble_css_included(self) -> None:
        """JS 側に speechTimeline 配列、UI に inner_thought トグル、CSS に .bubble.speech 等。"""
        out = render_viewer_html(
            title="t",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert "speechTimeline" in out
        assert 'id="toggle-thoughts"' in out
        assert "inner thought" in out  # チェックボックスラベル
        assert ".bubble.speech" in out
        assert ".bubble.thought" in out


class TestRenderViewerHtmlSiblingLinks:
    """episodic / timeline への遷移リンクが htmlpreview 経由でも壊れない仕掛けを確認する。"""

    def test_episodic_timeline_data_sibling_attribute_file(self) -> None:
        """相対 href だけだと htmlpreview 経由で raw gist (text/plain) に解決され
        ソース表示になるため、JS 書き換えの起点として data-sibling を持たせる。"""
        out = render_viewer_html(
            title="t",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert 'data-sibling="episodic.html"' in out
        assert 'data-sibling="timeline.html"' in out

    def test_htmlpreview_via_htmlpreview_url_js(self) -> None:
        """viewer 自身が htmlpreview.github.io 経由で配信されている場合、兄弟
        リンクも htmlpreview でラップした URL に書き換える JS が含まれる。"""
        out = render_viewer_html(
            title="t",
            events=_sample_events(),
            scenario_topology={"spots": [], "connections": []},
            cytoscape_js_src="/* fake */",
        )
        assert "htmlpreview.github.io" in out
        assert "data-sibling" in out

"""scripts/trace_to_html.py の HTML 生成テスト (Issue #188 Phase 1d)。"""

import sys
from pathlib import Path

import pytest

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import JsonlTraceRecorder

# scripts/ を import 可能にする
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.trace_to_html import (  # noqa: E402
    main,
    render_html,
)


def _sample_events() -> list[TraceEvent]:
    return [
        TraceEvent(
            seq=1,
            timestamp="2026-05-24T00:00:00+00:00",
            kind=TraceEventKind.RUN_START,
            payload={"run_id": "exp-01"},
        ),
        TraceEvent(
            seq=2,
            timestamp="2026-05-24T00:00:01+00:00",
            kind=TraceEventKind.OBSERVATION,
            tick=1,
            player_id=1,
            payload={"prose": "扉が軋む", "player_name": "カイト"},
        ),
        TraceEvent(
            seq=3,
            timestamp="2026-05-24T00:00:02+00:00",
            kind=TraceEventKind.ACTION,
            tick=1,
            player_id=1,
            payload={"tool": "press", "player_name": "カイト"},
        ),
        TraceEvent(
            seq=4,
            timestamp="2026-05-24T00:00:03+00:00",
            kind=TraceEventKind.ACTION_RESULT,
            tick=1,
            player_id=1,
            payload={"success": True, "result_summary": "press 成功"},
        ),
        TraceEvent(
            seq=5,
            timestamp="2026-05-24T00:00:04+00:00",
            kind=TraceEventKind.MEMO_ADD,
            tick=1,
            player_id=1,
            payload={"memo_id": "m1", "content": "扉を固定する"},
        ),
    ]


class TestRenderHtml:
    """render_html の HTML 出力構造。"""

    def test_メタ情報_と_mermaid_と_per_tick_が含まれる(self) -> None:
        """生成 HTML に主要 section ヘッダと mermaid ブロックが含まれる。"""
        out = render_html(_sample_events(), title="my-run")
        assert "<title>my-run" in out
        assert "メタ情報" in out
        assert "シーケンス図" in out
        assert "tick 別タイムライン" in out
        # mermaid block
        assert "sequenceDiagram" in out
        assert "mermaid.initialize" in out

    def test_player_label_は_player_name_を優先する(self) -> None:
        """payload.player_name が見つかれば actor label に使う。"""
        out = render_html(_sample_events())
        assert "カイト" in out

    def test_action_result_の_NG_は_failed_success_で分岐(self) -> None:
        """success=False の result は NG マークになる。"""
        events = list(_sample_events())
        events[3] = TraceEvent(
            seq=4,
            timestamp="2026-05-24T00:00:03+00:00",
            kind=TraceEventKind.ACTION_RESULT,
            tick=1,
            player_id=1,
            payload={"success": False, "result_summary": "失敗"},
        )
        out = render_html(events)
        assert "[NG]" in out


class TestMain:
    """CLI main エントリポイントの基本動作。"""

    def test_jsonl_から_html_を生成する(self, tmp_path: Path) -> None:
        """jsonl → html へ変換、出力パスが返る。"""
        jsonl = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(jsonl) as rec:
            rec.record(TraceEventKind.RUN_START, run_id="x")
            rec.record(
                TraceEventKind.OBSERVATION,
                tick=1,
                player_id=1,
                prose="物音",
                player_name="リン",
            )
        out_path = tmp_path / "trace.html"
        rc = main([str(jsonl), "-o", str(out_path)])
        assert rc == 0
        text = out_path.read_text(encoding="utf-8")
        assert "<title>trace" in text
        assert "リン" in text

    def test_出力パス未指定なら_拡張子を_html_に置換する(self, tmp_path: Path) -> None:
        """-o 省略時は input と同じ場所に .html を出す。"""
        jsonl = tmp_path / "auto.jsonl"
        with JsonlTraceRecorder(jsonl) as rec:
            rec.record(TraceEventKind.NOTE, message="hi")
        rc = main([str(jsonl)])
        assert rc == 0
        assert (tmp_path / "auto.html").exists()

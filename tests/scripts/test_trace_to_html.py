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

    def test_mermaid_per_tick_included(self) -> None:
        """生成 HTML に主要 section ヘッダと mermaid ブロックが含まれる。"""
        out = render_html(_sample_events(), title="my-run")
        assert "<title>my-run" in out
        assert "メタ情報" in out
        assert "シーケンス図" in out
        assert "tick 別タイムライン" in out
        # mermaid block
        assert "sequenceDiagram" in out
        assert "mermaid.initialize" in out

    def test_player_label_player_name_prefers(self) -> None:
        """payload.player_name が見つかれば actor label に使う。"""
        out = render_html(_sample_events())
        assert "カイト" in out

    def test_action_result_ng_failed_success(self) -> None:
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

    def test_mermaid_arrows_raw(self) -> None:
        """Mermaid のシーケンス矢印 ``->>`` / ``-->>`` が HTML エスケープされず
        リテラルで出力されること (描画バグの回帰防止)。

        ``&gt;&gt;`` になるとブラウザ環境によっては Mermaid パーサが
        decode しきれず syntax error になり描画されなくなる。
        """
        out = render_html(_sample_events(), title="my-run")
        # `<pre class="mermaid">` ブロック内に raw の `->>` / `-->>` がある
        # (fallback の raw-mermaid ブロックは html.escape 済みなのでそちらの
        # &gt;&gt; は OK)
        # 簡単にチェック: 全体に少なくとも 1 つ raw `->>` リテラルがある
        assert "->>" in out, "raw `->>` arrow not found in HTML"
        assert "-->>" in out, "raw `-->>` arrow not found in HTML"

    def test_actor_label_html_special_chars_are_fullwidth(self) -> None:
        """player_name に ``<`` / ``>`` / ``&`` が混入してもタグ解釈されない。"""
        events = [
            TraceEvent(
                seq=1,
                timestamp="2026-05-24T00:00:00+00:00",
                kind=TraceEventKind.ACTION,
                tick=1,
                player_id=1,
                payload={
                    "tool": "noop",
                    "player_name": "<script>alert(1)</script>",
                },
            ),
        ]
        out = render_html(events)
        # `<script>` が raw のまま actor 定義に埋め込まれていない
        assert "actor P1 as <script>" not in out
        # 代わりに全角化された文字列が入っている
        assert "＜script＞" in out

    def test_fallback_raw_mermaid_included(self) -> None:
        """CDN ブロック時用に mermaid raw source の <details> と mermaid.live リンクがある。"""
        out = render_html(_sample_events())
        assert "raw-mermaid" in out
        assert "mermaid.live" in out


class TestMain:
    """CLI main エントリポイントの基本動作。"""

    def test_jsonl_html(self, tmp_path: Path) -> None:
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

    def test_unspecified_html(self, tmp_path: Path) -> None:
        """-o 省略時は input と同じ場所に .html を出す。"""
        jsonl = tmp_path / "auto.jsonl"
        with JsonlTraceRecorder(jsonl) as rec:
            rec.record(TraceEventKind.NOTE, message="hi")
        rc = main([str(jsonl)])
        assert rc == 0
        assert (tmp_path / "auto.html").exists()

"""TraceEventKind.POSITION_CHANGE の存在と JSONL ラウンドトリップ確認。

実 runtime 経由の emit テストは world_runtime の重い fixture が要るため、
scripts/run_scenario_experiment の単体テスト側 (test_run_scenario_experiment.py)
で別途扱う。本ファイルは schema 単体の sanity check のみ。
"""

import json
from pathlib import Path

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import (
    JsonlTraceRecorder,
    load_trace_events,
)


class TestPositionChangeKind:
    """``POSITION_CHANGE`` event kind の schema 整合性。"""

    def test_TraceEventKind_に_POSITION_CHANGE_が定義されている(self) -> None:
        """新規 kind を追加した結果。"""
        assert TraceEventKind.POSITION_CHANGE == "position_change"

    def test_position_change_event_を_JSONL_に_書いて読み戻せる(self, tmp_path: Path) -> None:
        """recorder が新 kind を扱え、payload も含めて round-trip する。"""
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as rec:
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=5,
                player_id=1,
                from_spot_id="control_room",
                to_spot_id="corridor",
                spot_name="廊下",
                player_name="カイト",
            )
        events = list(load_trace_events(path))
        assert len(events) == 1
        ev = events[0]
        assert ev.kind == TraceEventKind.POSITION_CHANGE
        assert ev.tick == 5
        assert ev.player_id == 1
        assert ev.payload == {
            "from_spot_id": "control_room",
            "to_spot_id": "corridor",
            "spot_name": "廊下",
            "player_name": "カイト",
        }

    def test_初期配置は_from_spot_id_None_で記録できる(self, tmp_path: Path) -> None:
        """``run_start`` 直後の初期位置は from_spot_id=None で表現する規約。"""
        path = tmp_path / "trace.jsonl"
        with JsonlTraceRecorder(path) as rec:
            rec.record(
                TraceEventKind.POSITION_CHANGE,
                tick=0,
                player_id=1,
                from_spot_id=None,
                to_spot_id="entrance",
                spot_name="入口",
                player_name="カイト",
            )
        events = list(load_trace_events(path))
        ev = events[0]
        assert ev.payload["from_spot_id"] is None
        # JSON 越しに None が保持されること (null として書かれて None に戻る)
        raw = path.read_text(encoding="utf-8").strip()
        parsed = json.loads(raw)
        assert parsed["payload"]["from_spot_id"] is None

"""シナリオ実行のトレース記録 (Issue #188 Phase 1d 基盤)。

LLM エージェントが世界の中で何を見て / どう考えて / 何をしたかを、後から人間が
時系列で振り返れるように構造化イベントとして記録する。
出力形式は JSON Lines。各行が単一の TraceEvent。

`TraceRecorder` は demos / runtime / 実験スクリプトから呼ばれる中立な記録口。
"""

from ai_rpg_world.application.trace.events import (
    TraceEvent,
    TraceEventKind,
)
from ai_rpg_world.application.trace.recorder import (
    ITraceRecorder,
    JsonlTraceRecorder,
    NullTraceRecorder,
)

__all__ = [
    "TraceEvent",
    "TraceEventKind",
    "ITraceRecorder",
    "JsonlTraceRecorder",
    "NullTraceRecorder",
]

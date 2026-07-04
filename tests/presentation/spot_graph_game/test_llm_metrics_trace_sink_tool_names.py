"""``_LlmMetricsTraceSink`` が ``tool_names`` (= LLM がその tick に prompt の
tool list で見たツール名集合) を trace に書くことを保証する (PR-F)。

Y_after_issue621 の分析では「tend_to_player が prompt に載っていたか
わからない」という問題があった。``llm_call`` イベントに ``tool_names`` を
追加することで、tick ごとに「LLM が知っていた tool セット」が trace から
直接読めるようになる。これは:
- tool catalog の wiring が壊れていないかの監視
- Issue #621 のように新 tool を追加したとき、本当に prompt に流れたかの確認
- prompt cache の安定性チェック (= 毎 tick 同じ tool 集合か)
の用途に効く。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _LlmMetricsTraceSink,
)


def _make_metrics(**overrides):
    m = MagicMock()
    m.model = overrides.get("model", "test-model")
    m.wall_latency_ms = overrides.get("wall_latency_ms", 1000)
    m.prompt_tokens = overrides.get("prompt_tokens", 100)
    m.completion_tokens = overrides.get("completion_tokens", 10)
    m.cached_tokens = overrides.get("cached_tokens", 50)
    m.tps = overrides.get("tps", 10.0)
    m.success = overrides.get("success", True)
    m.error_code = overrides.get("error_code", None)
    m.cost_usd = overrides.get("cost_usd", 0.001)
    return m


def _make_runtime(tick: int = 5) -> MagicMock:
    rt = MagicMock()
    rt.current_tick.return_value = tick
    rt.bump_llm_call_count = MagicMock()
    return rt


class TestToolNamesRecorded:
    def test_tool_names_を_渡すと_trace_event_に_乗る(self) -> None:
        recorder = MagicMock()
        tool_names = ["explore", "speech_speak", "tend_to_player"]
        sink = _LlmMetricsTraceSink(
            trace_recorder=recorder,
            runtime=_make_runtime(),
            player_id=PlayerId(1),
            tool_names=tool_names,
        )
        sink.record(_make_metrics())

        recorder.record.assert_called_once()
        kwargs = recorder.record.call_args.kwargs
        assert kwargs["tool_names"] == tool_names

    def test_tool_names_未指定なら_空_list_で_記録される(self) -> None:
        """back-compat: 既存 caller (tool_names を渡さない) でも壊れない。"""
        recorder = MagicMock()
        sink = _LlmMetricsTraceSink(
            trace_recorder=recorder,
            runtime=_make_runtime(),
            player_id=PlayerId(1),
        )
        sink.record(_make_metrics())

        recorder.record.assert_called_once()
        kwargs = recorder.record.call_args.kwargs
        # 「指定なし」を明示する空 list で trace を埋めることで、後段の集計が
        # `tool_names` フィールドの有無を気にせず長さ判定だけで済む。
        assert kwargs["tool_names"] == []

    def test_既存のメトリクス_field_も_引き続き_記録される_regression(self) -> None:
        """tool_names 追加で既存 payload が落ちないこと。"""
        recorder = MagicMock()
        sink = _LlmMetricsTraceSink(
            trace_recorder=recorder,
            runtime=_make_runtime(tick=7),
            player_id=PlayerId(2),
            tool_names=["x"],
        )
        sink.record(_make_metrics(
            wall_latency_ms=1500, prompt_tokens=200,
            completion_tokens=25, cached_tokens=120,
            cost_usd=0.005,
        ))

        kwargs = recorder.record.call_args.kwargs
        assert kwargs["tick"] == 7
        assert kwargs["player_id"] == 2
        assert kwargs["wall_latency_ms"] == 1500
        assert kwargs["prompt_tokens"] == 200
        assert kwargs["completion_tokens"] == 25
        assert kwargs["cached_tokens"] == 120
        assert kwargs["cost_usd"] == 0.005
        assert kwargs["tool_names"] == ["x"]

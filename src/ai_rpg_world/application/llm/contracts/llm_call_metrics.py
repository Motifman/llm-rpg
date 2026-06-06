"""LLM 呼び出し 1 件分のメトリクス (実験 #356 / Step 1 後続)。

τ_sim の設定根拠、scenario ごとの cost / latency 評価、モデル選択の比較材料を
取るための薄い計測層。

設計指針:
- LLM 1 呼び出しのたびに 1 件、trace.jsonl に LLM_CALL kind で記録する
- 観測 (どのプレイヤーが、どの tick で、どの tool を選んだか) は trace event
  本体の field (tick / player_id) と payload の tool_name で取れる
- TTFT (Time To First Token) は streaming mode が要るので v0 では未収集。
  wall_latency_ms と tps から派生分析できる
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class LlmCallMetrics:
    """LLM 1 呼び出しの性能指標。

    Attributes:
        model: model 識別子 (例: "openai/gpt-5-mini", "anthropic/claude-sonnet-4-6")
        wall_latency_ms: 呼び出し開始 → 終了の壁時計 (HTTP RTT 含む全部)
        prompt_tokens: 入力トークン数 (litellm 経由で取れる場合)
        completion_tokens: 出力トークン数 (litellm 経由で取れる場合)
        tps: tokens per second (= completion_tokens / wall_seconds)。
            wall_latency_ms <= 0 の場合は 0.0
        success: tool_call が parse できたか / 例外なく終わったか
        error_code: 失敗時のエラー識別子 (例: "LLM_API_CALL_FAILED",
            "LLM_RATE_LIMIT", "NO_TOOL_CALL")
    """
    model: str
    wall_latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    tps: float
    success: bool
    error_code: Optional[str] = None

    @staticmethod
    def compute_tps(completion_tokens: int, wall_latency_ms: int) -> float:
        """tokens per second を安全に計算する (0 除算回避)。"""
        if wall_latency_ms <= 0 or completion_tokens <= 0:
            return 0.0
        return round(completion_tokens * 1000.0 / wall_latency_ms, 2)


class LlmCallMetricsSink(Protocol):
    """LLM 呼び出しメトリクスを受け取る sink。

    `LiteLLMClient.invoke` 等の実装が呼び出し完了時に `record(metrics)` を
    1 度だけ呼ぶ。sink 側は trace recorder への push / 集計などを行う。
    """

    def record(self, metrics: LlmCallMetrics) -> None: ...


__all__ = ["LlmCallMetrics", "LlmCallMetricsSink"]

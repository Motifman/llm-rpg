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

from ai_rpg_world.application.llm.ports.llm_client_port import ToolChoice


@dataclass(frozen=True)
class LlmCallMetrics:
    """LLM 1 呼び出しの性能指標。

    Attributes:
        model: model 識別子 (例: "openai/gpt-5-mini", "anthropic/claude-sonnet-4-6")
        wall_latency_ms: 呼び出し開始 → 終了の壁時計 (HTTP RTT 含む全部)
        prompt_tokens: 入力トークン数 (litellm 経由で取れる場合)
        completion_tokens: 出力トークン数 (litellm 経由で取れる場合)
        cached_tokens: prefix cache 経由で再利用された入力トークン数。
            provider が返さない場合は 0。vLLM / OpenAI は ``usage.prompt_tokens_details.cached_tokens``、
            Anthropic は ``usage.cache_read_input_tokens`` で返す
        reasoning_tokens: reasoning model が思考に使ったトークン数
            (``usage.completion_tokens_details.reasoning_tokens``)。reasoning OFF /
            非 reasoning model / 未対応 provider では 0。案A (band-gated thinking) で
            「実際にどれだけ熟考したか」の観測点になる (tool-calling 経路では思考
            本文は返らないため、このトークン数が発火の証拠になる)
        tps: tokens per second (= completion_tokens / wall_seconds)。
            wall_latency_ms <= 0 の場合は 0.0
        success: tool_call が parse できたか / 例外なく終わったか
        error_code: 失敗時のエラー識別子 (例: "LLM_API_CALL_FAILED",
            "LLM_RATE_LIMIT", "NO_TOOL_CALL")
        error_detail: 失敗時の例外本文 (provider 名・provider エラーコード等を含む
            生メッセージを truncate したもの)。成功時は空文字。error_code だけでは
            「なぜ失敗したか」が分からない (例: 400 の本文
            "Thinking mode does not support this tool_choice") ため、trace から
            事後診断できるように残す。
        reasoning_effort: この呼び出しで指定した reasoning の effort (案A の
            熟考ターンなら "low" 等、通常ターンは None)。熟考ターンと通常ターンを
            trace で区別し、reasoning 指定が失敗と相関するかを見るため。
        tool_choice: この呼び出しの tool_choice ("required" / "auto" 等)。
            reasoning との組合せ起因の provider 拒否を trace から切り分けるため。
            named tool_choice の場合は OpenAI 形式の dict をそのまま保持する。
        phase: 呼び出し区分。既存 1段階ターンは "one_step"。reason-first
            2段階ターンでは "assess_phase" / "action_phase" を入れ、同一 turn 内の
            2 呼び出しを trace / prompt dataset で区別する。
        cost_usd: 1 呼び出し分の USD コスト。provider 側が usage に乗せて返した値を
            そのまま使う (= モデル価格表をコード側で持たない / 値段改定の追従不要)。
            OpenRouter は ``extra_body.usage.include=true`` を付けると ``usage.cost``
            を返す。OpenAI 直結 / vLLM 等は返さないので 0.0。
            **provider の宣告値**なので、二重課金監査用ではなく実験コスト感の把握用。
    """
    model: str
    wall_latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    tps: float
    success: bool
    error_code: Optional[str] = None
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    error_detail: str = ""
    reasoning_effort: Optional[str] = None
    tool_choice: ToolChoice = ""
    phase: str = "one_step"
    llm_call_id: Optional[str] = None

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

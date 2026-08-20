"""Phase A LLM metrics を trace に流す sink。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

class LlmMetricsTraceSink:
    """Phase A の LLM 呼び出し metrics を trace に流す sink (PR #358)。

    Review HIGH 2 対応: current_tick は ``record()`` 呼び出し時点で取得する
    (sink 構築時に固定すると、遅い LLM 呼び出しが tick 境界を跨いだ場合に
    stale tick で記録される。後の τ_sim 分析の信頼性に関わる)。

    Review MEDIUM 対応: 旧実装は inner class を毎呼び出し定義していたが、
    parallel hot path で無駄なので module-level に切り出した。
    """

    def __init__(
        self,
        trace_recorder: Any,
        runtime: Any,
        player_id: PlayerId,
        tool_names: Optional[list[str]] = None,
    ) -> None:
        self._trace_recorder = trace_recorder
        self._runtime = runtime
        self._player_id_value = int(player_id.value)
        # PR-F: LLM がその tick の prompt で実際に見たツール名集合。trace に
        # 残すことで「tend_to_player が本当に prompt に流れたか」「tool catalog
        # の wiring が壊れていないか」「prompt の tool 集合が tick ごとに
        # 安定しているか (= cache key 安定性)」が後から検証できる。
        # 未指定 (= 既存 caller) は空 list として記録する (= 「明示的に
        # 渡さなかった」を「不在」と区別しないシンプル運用)。
        self._tool_names: list[str] = list(tool_names) if tool_names else []

    def record(self, metrics: Any) -> None:
        try:
            tick: Optional[int] = None
            try:
                tick = int(self._runtime.current_tick())
            except Exception:
                tick = None
            self._trace_recorder.record(
                TraceEventKind.LLM_CALL,
                tick=tick,
                player_id=self._player_id_value,
                model=metrics.model,
                wall_latency_ms=metrics.wall_latency_ms,
                prompt_tokens=metrics.prompt_tokens,
                completion_tokens=metrics.completion_tokens,
                cached_tokens=metrics.cached_tokens,
                # 案A (band-gated thinking) の効果測定用。tool-calling 経路では
                # 思考本文が返らないため、AGENT_REASONING_ENGAGED と同 tick の
                # この値を突き合わせて「実際にどれだけ熟考したか」を事後計算する。
                reasoning_tokens=metrics.reasoning_tokens,
                tps=metrics.tps,
                success=metrics.success,
                error_code=metrics.error_code,
                # 失敗観測性: error_code だけでは「なぜ失敗したか」が分からないので
                # 例外本文 (provider 名・400 の本文等) を残す。reasoning_effort /
                # tool_choice で「熟考ターンか」「required 起因の拒否か」を trace
                # だけで切り分けられるようにする (実 run v3coop_stagnation_002 の
                # 「Thinking mode does not support this tool_choice」診断が
                # trace から即できなかった穴を塞ぐ)。
                error_detail=getattr(metrics, "error_detail", ""),
                reasoning_effort=getattr(metrics, "reasoning_effort", None),
                tool_choice=getattr(metrics, "tool_choice", ""),
                phase=getattr(metrics, "phase", "one_step"),
                llm_call_id=getattr(metrics, "llm_call_id", None),
                discarded_tool_calls=getattr(metrics, "discarded_tool_calls", 0),
                **(
                    {"tool_call_combination": list(metrics.tool_call_combination)}
                    if getattr(metrics, "tool_call_combination", None) is not None
                    else {}
                ),
                # OpenRouter 経由のとき usage.cost (USD) が乗る。直結 / vLLM では 0.0。
                # 実験 trace を見れば cost 合計が事後計算できる。
                cost_usd=getattr(metrics, "cost_usd", 0.0),
                # PR-F: LLM 視点での「見えていた tool 一覧」。
                tool_names=list(self._tool_names),
            )
            # #404 P2: progress.jsonl 用 LLM 呼び出しカウンタを bump。
            # runtime 側に counter が無いランタイム (presentation 単体テスト等)
            # は getattr で安全に skip する。
            bump = getattr(self._runtime, "bump_llm_call_count", None)
            if callable(bump):
                try:
                    bump()
                except Exception:
                    # counter 失敗は trace 記録自体を壊さない
                    pass
        except Exception:
            logger.exception("trace_recorder.record(llm_call) failed")

"""LLM が連続で落ちはじめた run は、自分で止まる。

供物競争 140 tick run は t47 で OpenRouter のクレジットが尽き、**以降 94 tick を
誰も行動せずに走り切った**。`make experiment` は exit 0、report.md は「140 tick
完走・全員 18〜20 行動」と書いた。呼び出しの半分が落ちたことは、trace を自分で
数えるまで見えなかった。

既存の砦 (`_classify_llm_run_health`) は **成功が 0 件のとき**しか働かない。この run
は前半に 76 件成功していたので通過した。履歴の壊れた run 3 本のうち、既存の砦が
捕まえるのは認証ミス (成功率 0%) の 1 本だけである。

停止の判断は**サーバが名乗る理由ではなく、retry を尽くしたあとの「治らなさ」**で
行う。判定そのものは `LlmFailureStreakMonitor` の試験が見る。ここが見るのは
**実走経路の配線** — 呼び出しの結末が runtime に届き、runtime が止まれと答えるか。
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _Metrics:
    """`LlmMetricsTraceSink.record` が受け取る metrics の最小形。"""

    def __init__(self, *, success: bool, error_code: str = "") -> None:
        self.model = "test-model"
        self.wall_latency_ms = 1
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.reasoning_tokens = 0
        self.tps = 0.0
        self.success = success
        self.error_code = error_code
        self.error_detail = ""


class _Recorder:
    def record(self, *args: Any, **kwargs: Any) -> None:
        return None


def _runtime(threshold: Optional[int] = None) -> Any:
    """閾値だけを差し替えた runtime を、実物の組み立て経路で作る。"""
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    values = {}
    if threshold is not None:
        values["LLM_FAILURE_STREAK_ABORT"] = str(threshold)
    return create_world_runtime(
        "data/scenarios/offering_race_v2.json",
        config=ResolvedLlmRuntimeConfig.from_mapping(values),
    )


def _sink(runtime: Any) -> Any:
    from ai_rpg_world.application.llm.services.world_llm_turn.metrics_sink import (
        LlmMetricsTraceSink,
    )

    return LlmMetricsTraceSink(_Recorder(), runtime, PlayerId(1))


class TestTheOutcomeOfEveryCallReachesTheRuntime:
    """呼び出しの結末が、trace を経由せずに runtime へ届く。"""

    def test_consecutive_failures_make_the_runtime_ask_to_stop(self) -> None:
        """閾値ぶん連続で失敗すると、runtime が停止理由を返す。

        **trace を読み直さずに判定できることが要件。** run の途中で
        trace.jsonl を数え直す形にすると、tick ごとにファイル全体を舐める。
        """
        runtime = _runtime(threshold=3)
        sink = _sink(runtime)

        for _ in range(3):
            sink.record(_Metrics(success=False, error_code="LLM_API_CALL_FAILED"))

        reason = runtime.llm_abort_reason()

        assert reason is not None
        assert "3" in reason
        assert "LLM_API_CALL_FAILED" in reason

    def test_a_healthy_run_is_never_asked_to_stop(self) -> None:
        """失敗が散発する run は止まらない (**負の対照**)。

        履歴で最も荒れた健全 run (成功率 79%) の形。ここが効かないと、
        **止めるべきでない run を engine が殺す**。
        """
        runtime = _runtime(threshold=3)
        sink = _sink(runtime)

        for _ in range(30):
            sink.record(_Metrics(success=False, error_code="LLM_API_CALL_FAILED"))
            sink.record(_Metrics(success=True))

        assert runtime.llm_abort_reason() is None

    def test_a_quiet_run_is_never_asked_to_stop(self) -> None:
        """呼び出しが 1 件も無い run は止まらない (**負の対照**)。"""
        runtime = _runtime(threshold=3)

        assert runtime.llm_abort_reason() is None

    def test_recording_still_bumps_the_progress_counter(self) -> None:
        """既存の progress 用カウンタを壊していない (**正の対照**)。

        同じ sink に 2 つ目の役目を足したので、先客が消えていないことを見る。
        """
        runtime = _runtime(threshold=3)
        sink = _sink(runtime)

        sink.record(_Metrics(success=True))

        assert runtime.pop_llm_call_count() == 1


class TestTheThresholdIsAnExperimentCondition:
    """停止の閾値が、実験条件として profile から動かせる。"""

    def test_the_default_is_eight(self) -> None:
        """既定は 8。健全な run の最長 (4) と壊れた run の最短 (35) の間。"""
        config = ResolvedLlmRuntimeConfig.from_mapping({})

        assert config.llm_failure_streak_abort == 8

    def test_a_profile_can_change_it(self) -> None:
        """profile の `LLM_FAILURE_STREAK_ABORT` が解決値に反映される。"""
        config = ResolvedLlmRuntimeConfig.from_mapping(
            {"LLM_FAILURE_STREAK_ABORT": "20"}
        )

        assert config.llm_failure_streak_abort == 20

    def test_zero_disables_the_abort(self) -> None:
        """0 を渡すと、何件連続で落ちても停止しない。

        「止める」を engine に持たせたくない run のための逃げ道。
        """
        runtime = _runtime(threshold=0)
        sink = _sink(runtime)

        for _ in range(50):
            sink.record(_Metrics(success=False, error_code="LLM_API_CALL_FAILED"))

        assert runtime.llm_abort_reason() is None

    def test_a_negative_threshold_is_rejected_at_startup(self) -> None:
        """負の閾値は設定の解決時に落ちる (壊れた条件で run を始めない)。"""
        with pytest.raises(ValueError):
            ResolvedLlmRuntimeConfig.from_mapping({"LLM_FAILURE_STREAK_ABORT": "-1"})

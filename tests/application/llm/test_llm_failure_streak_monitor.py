"""恒久的な LLM 障害を「治らなさ」で判定する監視の挙動を保証する。

## なぜ「理由」で判定しないか

供物競争 140 tick run は t47 で OpenRouter のクレジットが尽き、以降 94 tick を
誰も行動せずに走り切った。それでも `make experiment` は exit 0 で、report.md は
「140 tick 完走」と書いた。

**68 件の失敗はすべて `in_flight_budget_exhausted` と名乗っていた** — OpenRouter の
文言では「in-flight が捌けば直る」= 一時エラーである。実際は残高 0 で、待っても
永久に直らなかった。**サーバが名乗る理由と、本当に回復するかは一致しない。**

そこで retry は理由で決め (429 / 5xx / 402 を短く再試行)、**run を止めるかどうかは
「retry を尽くしてなお連続で落ちた回数」で決める**。理由の分類に依存しないので、
未知のエラーや新しい 402 の亜種でも効く。

## 閾値 8 の根拠

`var/runs/` の 68 run で最長連続失敗を数えた。

| | 最長連続失敗 |
|---|---|
| 健全な 65 run | 0〜4 |
| DigitalOcean 速度崩壊 (成功率 12%) | 35 |
| 認証ミス (成功率 0%) | 45 |
| クレジット切れ (成功率 51%) | 64 |

8 は両側に 2 倍の余裕を持って分離する。
"""

from __future__ import annotations

import threading

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.llm_failure_streak_monitor import (  # noqa: E501
    DEFAULT_FAILURE_STREAK_ABORT,
    LlmFailureStreakMonitor,
)


class TestTheStreakCounts:
    """連続した失敗だけを数える。"""

    def test_consecutive_failures_accumulate(self) -> None:
        """失敗を重ねると streak がその件数まで増える。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        for _ in range(3):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        assert monitor.streak == 3

    def test_a_single_success_clears_the_streak(self) -> None:
        """成功 1 件で streak が 0 に戻る (**負の対照**)。

        ここが効かないと、run 全体でぽつぽつ落ちるだけの健全な run
        (履歴では成功率 79〜99%) が累計で閾値に達して殺される。
        """
        monitor = LlmFailureStreakMonitor(threshold=8)
        for _ in range(7):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        monitor.record(success=True, error_code="")

        assert monitor.streak == 0
        assert monitor.is_tripped() is False

    def test_scattered_failures_never_trip(self) -> None:
        """失敗と成功が交互に来る run は、失敗が何件あっても止まらない。

        履歴で最も荒れた健全 run (station_drill_038、成功率 79%) の形。
        """
        monitor = LlmFailureStreakMonitor(threshold=8)

        for _ in range(50):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")
            monitor.record(success=True, error_code="")

        assert monitor.is_tripped() is False


class TestTheThreshold:
    """閾値に達したときだけ止める判断を出す。"""

    def test_it_trips_exactly_at_the_threshold(self) -> None:
        """閾値と同数の連続失敗で tripped になる。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        for _ in range(8):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        assert monitor.is_tripped() is True

    def test_one_short_of_the_threshold_does_not_trip(self) -> None:
        """閾値より 1 件少ない連続失敗では tripped にならない (境界)。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        for _ in range(7):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        assert monitor.is_tripped() is False

    def test_tripping_is_sticky(self) -> None:
        """一度 tripped になったら、あとから成功が着地しても解除しない。

        並列 Phase A では、停止を決めた後に走っていた呼び出しが遅れて成功で
        戻ることがある。**そこで解除すると停止判断が呼び出しの着順で揺れる。**
        """
        monitor = LlmFailureStreakMonitor(threshold=3)
        for _ in range(3):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        monitor.record(success=True, error_code="")

        assert monitor.is_tripped() is True

    def test_a_threshold_of_zero_disables_the_abort(self) -> None:
        """閾値 0 は監視を無効にする (何件連続で落ちても tripped にならない)。

        「止める」を engine に持たせたくない run のための逃げ道。
        """
        monitor = LlmFailureStreakMonitor(threshold=0)

        for _ in range(100):
            monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        assert monitor.is_tripped() is False
        assert monitor.streak == 100

    def test_a_negative_threshold_is_rejected(self) -> None:
        """負の閾値は構築時に ValueError で落ちる。"""
        with pytest.raises(ValueError):
            LlmFailureStreakMonitor(threshold=-1)

    def test_the_default_threshold_is_eight(self) -> None:
        """既定の閾値は 8。健全な run の最長 (4) と壊れた run の最短 (35) の間。"""
        assert DEFAULT_FAILURE_STREAK_ABORT == 8


class TestItExplainsWhyItTripped:
    """止めた理由を、人が読める 1 行にする。"""

    def test_the_description_names_the_streak_and_the_error_codes(self) -> None:
        """連続件数と、その連続に出た error_code の内訳を含む。

        error_code が無いと「何が起きて止まったか」を trace から探し直す
        ことになる。**止めた判断の根拠は、止めた場所に書く。**
        """
        monitor = LlmFailureStreakMonitor(threshold=3)
        monitor.record(success=False, error_code="LLM_API_CALL_FAILED")
        monitor.record(success=False, error_code="LLM_API_CALL_FAILED")
        monitor.record(success=False, error_code="LLM_NO_TOOL_CALL")

        description = monitor.describe()

        assert "3" in description
        assert "LLM_API_CALL_FAILED: 2" in description
        assert "LLM_NO_TOOL_CALL: 1" in description

    def test_the_breakdown_only_covers_the_current_streak(self) -> None:
        """成功で切れる前の失敗は内訳に混ざらない。

        run 全体の内訳は report.md が出す。ここは**止めた連続**の中身だけを
        説明する — 混ぜると「何が止めたか」が読めなくなる。
        """
        monitor = LlmFailureStreakMonitor(threshold=2)
        monitor.record(success=False, error_code="LLM_WALL_TIME_CAP")
        monitor.record(success=True, error_code="")
        monitor.record(success=False, error_code="LLM_API_CALL_FAILED")
        monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        description = monitor.describe()

        assert "LLM_WALL_TIME_CAP" not in description
        assert "LLM_API_CALL_FAILED: 2" in description

    def test_an_unnamed_error_still_appears(self) -> None:
        """error_code が空でも内訳に UNKNOWN として出る。

        名前が無い失敗が黙って消えると、件数と内訳の合計が合わなくなる。
        """
        monitor = LlmFailureStreakMonitor(threshold=1)
        monitor.record(success=False, error_code="")

        assert "UNKNOWN: 1" in monitor.describe()


class TestItSurvivesParallelTurns:
    """並列 Phase A から同時に呼ばれても数え落ちない。"""

    def test_no_records_are_lost_under_threads(self) -> None:
        """8 スレッドから 100 件ずつ失敗を記録して、streak が 800 になる。

        Phase A は ThreadPoolExecutor で走る (実験 profile は 8 worker)。
        **数え落ちは「止まるべき run が止まらない」側に倒れる。**
        """
        monitor = LlmFailureStreakMonitor(threshold=0)

        def hammer() -> None:
            for _ in range(100):
                monitor.record(success=False, error_code="LLM_API_CALL_FAILED")

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert monitor.streak == 800

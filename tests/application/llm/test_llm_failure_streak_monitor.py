"""恒久的な LLM 障害を「治らなさ」で判定する監視の挙動を保証する。

## なぜ「理由」で判定しないか

供物競争 140 tick run は t47 で OpenRouter のクレジットが尽き、以降 94 tick を
誰も行動せずに走り切った。それでも `make experiment` は exit 0 で、report.md は
「140 tick 完走」と書いた。

**クレジット切れの 68 件はすべて `in_flight_budget_exhausted` と名乗っていた** —
OpenRouter の文言では「in-flight が捌ければ直る」= 一時エラーである。実際は残高 0
で、待っても永久に直らなかった。**サーバが名乗る理由と、本当に回復するかは
一致しない。**

そこで retry は理由で決め (429 / 5xx を短く再試行)、**run を止めるかどうかは
「retry を尽くしてなお連続で落ちた回数」で決める**。理由の分類に依存しないので、
未知のエラーや新しい 402 の亜種でも効く。

## 止める条件は 2 つある

`var/runs/` の 68 run で校正した。

| | 最長連続失敗 |
|---|---|
| 健全な 65 run | 0〜4 |
| DigitalOcean 速度崩壊 (成功率 12%) | 35 |
| 認証ミス (成功率 0%) | 45 |
| クレジット切れ (成功率 51%) | 64 |

件数だけでは足りない。**8 エージェント run は 1 tick に最大 9 件呼ぶ**ので、
「全員が同時に 1 回落ちる」だけで閾値 8 に届く。しかも履歴の失敗の主因は
wall-time cap の Timeout (343 件中 168 件) で、これは retry 対象外なので provider が
数十秒遅くなった瞬間のバーストはそのまま届く。

そこで **連続が 2 つ以上の tick にまたがること**を条件に足す。壊れた 3 本の最初の
8 連続はそれぞれ 4 / 2 / 2 tick にまたがるので、**検出は 1 本も失わずに、単一 tick
のバーストによる誤検知だけが構造的に消える**。
"""

from __future__ import annotations

import threading

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.llm_failure_streak_monitor import (  # noqa: E501
    DEFAULT_FAILURE_STREAK_ABORT,
    LlmFailureStreakMonitor,
)

_FAIL = "LLM_API_CALL_FAILED"


def _fail_across_ticks(monitor: LlmFailureStreakMonitor, count: int) -> None:
    """1 件ずつ別の tick で失敗させる (tick の条件を満たす形)。"""
    for index in range(count):
        monitor.record(success=False, error_code=_FAIL, tick=index)


class TestTheStreakCounts:
    """連続した失敗だけを数える。"""

    def test_consecutive_failures_accumulate(self) -> None:
        """失敗を重ねると streak がその件数まで増える。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        _fail_across_ticks(monitor, 3)

        assert monitor.streak == 3

    def test_a_single_success_clears_the_streak(self) -> None:
        """成功 1 件で streak が 0 に戻る (**負の対照**)。

        ここが効かないと、run 全体でぽつぽつ落ちるだけの健全な run
        (履歴では成功率 79〜99%) が累計で閾値に達して殺される。
        """
        monitor = LlmFailureStreakMonitor(threshold=8)
        _fail_across_ticks(monitor, 7)

        monitor.record(success=True, tick=7)

        assert monitor.streak == 0
        assert monitor.is_tripped() is False

    def test_scattered_failures_never_trip(self) -> None:
        """失敗と成功が交互に来る run は、失敗が何件あっても止まらない。

        履歴で最も荒れた健全 run (station_drill_038、成功率 79%) の形。
        """
        monitor = LlmFailureStreakMonitor(threshold=8)

        for tick in range(50):
            monitor.record(success=False, error_code=_FAIL, tick=tick)
            monitor.record(success=True, tick=tick)

        assert monitor.is_tripped() is False


class TestTheThreshold:
    """閾値に達したときだけ止める判断を出す。"""

    def test_it_trips_exactly_at_the_threshold(self) -> None:
        """閾値と同数の連続失敗で tripped になる。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        _fail_across_ticks(monitor, 8)

        assert monitor.is_tripped() is True

    def test_one_short_of_the_threshold_does_not_trip(self) -> None:
        """閾値より 1 件少ない連続失敗では tripped にならない (境界)。"""
        monitor = LlmFailureStreakMonitor(threshold=8)

        _fail_across_ticks(monitor, 7)

        assert monitor.is_tripped() is False

    def test_a_threshold_of_zero_disables_the_abort(self) -> None:
        """閾値 0 は監視を無効にする (何件連続で落ちても tripped にならない)。

        「止める」を engine に持たせたくない run のための逃げ道。
        """
        monitor = LlmFailureStreakMonitor(threshold=0)

        _fail_across_ticks(monitor, 100)

        assert monitor.is_tripped() is False
        assert monitor.streak == 100

    def test_a_negative_threshold_is_rejected(self) -> None:
        """負の閾値は構築時に ValueError で落ちる。"""
        with pytest.raises(ValueError):
            LlmFailureStreakMonitor(threshold=-1)

    def test_the_default_threshold_is_eight(self) -> None:
        """既定の閾値は 8。健全な run の最長 (4) と壊れた run の最短 (35) の間。"""
        assert DEFAULT_FAILURE_STREAK_ABORT == 8


class TestABurstInsideOneTickIsNotAnOutage:
    """1 tick の中で全員が同時に落ちただけでは止めない。"""

    def test_a_single_tick_burst_never_trips(self) -> None:
        """同じ tick の失敗だけでは、件数が閾値を超えても tripped にならない。

        8 エージェント run は 1 tick に最大 9 件呼ぶ。provider が一瞬遅く
        なって全員が wall-time cap に当たるだけで閾値 8 に届いてしまう。
        **「治らなさ」は時間をまたいで初めて観測できる。**
        """
        monitor = LlmFailureStreakMonitor(threshold=8)

        for _ in range(20):
            monitor.record(success=False, error_code=_FAIL, tick=42)

        assert monitor.streak == 20
        assert monitor.is_tripped() is False

    def test_the_next_tick_completes_the_condition(self) -> None:
        """次の tick に 1 件でも失敗が続けば tripped になる (**正の対照**)。

        tick の条件が「永久に止まらない」に化けていないことを見る。
        """
        monitor = LlmFailureStreakMonitor(threshold=8)
        for _ in range(8):
            monitor.record(success=False, error_code=_FAIL, tick=42)
        assert monitor.is_tripped() is False

        monitor.record(success=False, error_code=_FAIL, tick=43)

        assert monitor.is_tripped() is True

    def test_an_unknown_tick_does_not_block_the_abort(self) -> None:
        """tick を渡せない呼び出し元でも停止できる (**負の対照**)。

        tick は `runtime.current_tick()` から取るので None になりうる。
        **不明を「同じ tick」と読むと、監視が黙って無効になる。**
        """
        monitor = LlmFailureStreakMonitor(threshold=3)

        for _ in range(3):
            monitor.record(success=False, error_code=_FAIL, tick=None)

        assert monitor.is_tripped() is True


class TestItExplainsWhyItTripped:
    """止めた理由を、人が読める 1 行にする。"""

    def test_the_description_names_the_streak_and_the_error_codes(self) -> None:
        """連続件数と、その連続に出た error_code の内訳を含む。

        error_code が無いと「何が起きて止まったか」を trace から探し直す
        ことになる。**止めた判断の根拠は、止めた場所に書く。**
        """
        monitor = LlmFailureStreakMonitor(threshold=3)
        monitor.record(success=False, error_code=_FAIL, tick=1)
        monitor.record(success=False, error_code=_FAIL, tick=2)
        monitor.record(success=False, error_code="LLM_NO_TOOL_CALL", tick=3)

        description = monitor.describe()

        assert "3" in description
        assert f"{_FAIL}: 2" in description
        assert "LLM_NO_TOOL_CALL: 1" in description

    def test_the_reason_survives_a_late_success(self) -> None:
        """止めたあとに遅れて成功が着地しても、理由が空にならない。

        停止判定は tick の全 worker が着地したあとに 1 回走る。**8 件目で
        止めた直後に 9 件目が成功で戻ると、streak が 0 にリセットされて
        「0 件連続で失敗した ()」が report と trace に載っていた。**
        止まるのに、なぜ止めたかが消える形だった。
        """
        monitor = LlmFailureStreakMonitor(threshold=3)
        _fail_across_ticks(monitor, 3)

        monitor.record(success=True, tick=99)

        assert f"{_FAIL}: 3" in monitor.describe()
        assert "3 件連続" in monitor.describe()

    def test_the_breakdown_only_covers_the_streak_that_tripped(self) -> None:
        """成功で切れる前の失敗は内訳に混ざらない。

        run 全体の内訳は report.md が出す。ここは**止めた連続**の中身だけを
        説明する — 混ぜると「何が止めたか」が読めなくなる。
        """
        monitor = LlmFailureStreakMonitor(threshold=2)
        monitor.record(success=False, error_code="LLM_WALL_TIME_CAP", tick=1)
        monitor.record(success=True, tick=2)
        monitor.record(success=False, error_code=_FAIL, tick=3)
        monitor.record(success=False, error_code=_FAIL, tick=4)

        description = monitor.describe()

        assert "LLM_WALL_TIME_CAP" not in description
        assert f"{_FAIL}: 2" in description

    def test_an_unnamed_error_still_appears(self) -> None:
        """error_code が空でも内訳に UNKNOWN として出る。

        名前が無い失敗が黙って消えると、件数と内訳の合計が合わなくなる。
        """
        monitor = LlmFailureStreakMonitor(threshold=2)
        monitor.record(success=False, error_code="", tick=1)
        monitor.record(success=False, error_code=_FAIL, tick=2)

        assert "UNKNOWN: 1" in monitor.describe()

    def test_a_healthy_monitor_describes_nothing(self) -> None:
        """止めていない監視は空文字を返す (**負の対照**)。"""
        monitor = LlmFailureStreakMonitor(threshold=8)
        _fail_across_ticks(monitor, 2)

        assert monitor.describe() == ""


class TestItSurvivesParallelTurns:
    """並列 Phase A から同時に呼ばれても数え落ちない。"""

    def test_no_records_are_lost_under_threads(self) -> None:
        """8 スレッドから 100 件ずつ失敗を記録して、streak が 800 になる。

        Phase A は ThreadPoolExecutor で走る (実験 profile は 8 worker)。
        **数え落ちは「止まるべき run が止まらない」側に倒れる。**

        なお CPython の GIL 下ではロックを外してもこの規模では落ちない。
        **この試験はロックの証明ではなく、壊れていないことの確認である。**
        """
        monitor = LlmFailureStreakMonitor(threshold=0)

        def hammer() -> None:
            for tick in range(100):
                monitor.record(success=False, error_code=_FAIL, tick=tick)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert monitor.streak == 800

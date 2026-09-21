"""連続した LLM 呼び出しの失敗を数え、恒久障害を「治らなさ」で判定する。"""

from __future__ import annotations

import threading

#: 既定の停止閾値。`var/runs/` の 68 run では健全な run の最長連続失敗が 4、
#: 壊れた run (速度崩壊 35 / 認証ミス 45 / クレジット切れ 64) の最短が 35 だった。
DEFAULT_FAILURE_STREAK_ABORT = 8

#: 連続が「時間をまたいだ」と認める最小の tick 数。8 エージェント run は 1 tick に
#: 最大 9 件呼ぶので、件数だけを見ると全員の同時失敗 1 回で閾値に届く。
_MIN_DISTINCT_TICKS = 2

_UNKNOWN_ERROR_CODE = "UNKNOWN"


class LlmFailureStreakMonitor:
    """連続失敗を数え、閾値に達したら「止めるべき」と答える。

    retry は例外の種類で決まる (`litellm_client._is_retryable_transient_error`)。
    こちらは **retry を尽くしたあとの結果だけ**を見るので、サーバが名乗る理由に
    依存しない。実際 OpenRouter のクレジット切れは 68 件すべてが
    `in_flight_budget_exhausted` (= 文言上は一時エラー) を名乗った。

    止める条件は 2 つ。**閾値ぶん連続して落ちること**と、**その連続が 2 つ以上の
    tick にまたがること**。後者が無いと、provider が一瞬遅くなって全員が
    wall-time cap に当たるだけで止まる (履歴の失敗の主因は Timeout で、これは
    retry 対象外なのでそのまま届く)。
    """

    def __init__(self, *, threshold: int = DEFAULT_FAILURE_STREAK_ABORT) -> None:
        if threshold < 0:
            raise ValueError("threshold must be 0 or greater")
        self._threshold = int(threshold)
        self._lock = threading.Lock()
        self._streak = 0
        self._streak_error_codes: list[str] = []
        self._streak_ticks: set[int] = set()
        #: 止めた瞬間の連続を凍結して持つ。並列 Phase A では停止を決めたあとに
        #: 遅れて成功が着地し、生のカウンタは 0 に戻る。**止まるのに「0 件連続で
        #: 失敗した ()」が report と trace に載る**形だった。
        self._tripped_reason: str | None = None

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def streak(self) -> int:
        with self._lock:
            return self._streak

    def record(
        self,
        *,
        success: bool,
        error_code: str = "",
        tick: int | None = None,
    ) -> None:
        """呼び出し 1 件の結末を記録する。

        `tick` は連続が時間をまたいだかの判定に使う。**不明 (None) は「同じ
        tick」ではなく「別の tick」として数える** — 不明を同一扱いにすると、
        tick を渡せない呼び出し元では監視が黙って無効になる。
        """
        with self._lock:
            if success:
                self._streak = 0
                self._streak_error_codes = []
                self._streak_ticks = set()
                return
            self._streak += 1
            self._streak_error_codes.append(str(error_code) or _UNKNOWN_ERROR_CODE)
            # tick が無い失敗も 1 回として数えるため、重複しない負値を入れる
            self._streak_ticks.add(tick if tick is not None else -len(self._streak_ticks) - 1)
            if self._tripped_reason is None and self._should_trip():
                self._tripped_reason = self._describe_locked()

    def _should_trip(self) -> bool:
        if not self._threshold:
            return False
        if self._streak < self._threshold:
            return False
        return len(self._streak_ticks) >= _MIN_DISTINCT_TICKS

    def is_tripped(self) -> bool:
        """止めるべき状態に入ったか。

        一度立ったら下ろさない。並列 Phase A では停止を決めたあとに走っていた
        呼び出しが遅れて成功で戻ることがあり、そこで解除すると停止判断が
        呼び出しの着順で揺れる。
        """
        with self._lock:
            return self._tripped_reason is not None

    def describe(self) -> str:
        """止めた連続の中身を 1 行で説明する。止めていなければ空文字。

        run 全体の内訳は report.md が出す。ここは**止めた連続**だけを見る。
        """
        with self._lock:
            return self._tripped_reason or ""

    def _describe_locked(self) -> str:
        breakdown = ", ".join(
            f"{code}: {count}" for code, count in _count_codes(self._streak_error_codes)
        )
        return f"LLM 呼び出しが {self._streak} 件連続で失敗した ({breakdown})"


def _count_codes(codes: list[str]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return sorted(counts.items())

"""連続した LLM 呼び出しの失敗を数え、恒久障害を「治らなさ」で判定する。"""

from __future__ import annotations

import threading
from typing import Dict, List, Tuple

#: 既定の停止閾値。`var/runs/` の 68 run では健全な run の最長連続失敗が 4、
#: 壊れた run (速度崩壊 35 / 認証ミス 45 / クレジット切れ 64) の最短が 35 だった。
DEFAULT_FAILURE_STREAK_ABORT = 8

_UNKNOWN_ERROR_CODE = "UNKNOWN"


class LlmFailureStreakMonitor:
    """連続失敗を数え、閾値に達したら「止めるべき」と答える。

    retry は例外の種類で決まる (`litellm_client._is_retryable_transient_error`)。
    こちらは **retry を尽くしたあとの結果だけ**を見るので、サーバが名乗る理由に
    依存しない。実際 OpenRouter のクレジット切れは 68 件すべてが
    `in_flight_budget_exhausted` (= 文言上は一時エラー) を名乗った。
    """

    def __init__(self, *, threshold: int = DEFAULT_FAILURE_STREAK_ABORT) -> None:
        if threshold < 0:
            raise ValueError("threshold must be 0 or greater")
        self._threshold = int(threshold)
        self._lock = threading.Lock()
        self._streak = 0
        self._streak_error_codes: List[str] = []
        self._tripped = False

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def streak(self) -> int:
        with self._lock:
            return self._streak

    def record(self, *, success: bool, error_code: str = "") -> None:
        """呼び出し 1 件の結末を記録する。"""
        with self._lock:
            if success:
                self._streak = 0
                self._streak_error_codes = []
                return
            self._streak += 1
            self._streak_error_codes.append(str(error_code) or _UNKNOWN_ERROR_CODE)
            if self._threshold and self._streak >= self._threshold:
                self._tripped = True

    def is_tripped(self) -> bool:
        """止めるべき状態に入ったか。

        一度立ったら下ろさない。並列 Phase A では停止を決めたあとに走っていた
        呼び出しが遅れて成功で戻ることがあり、そこで解除すると停止判断が
        呼び出しの着順で揺れる。
        """
        with self._lock:
            return self._tripped

    def describe(self) -> str:
        """止めた連続の中身を 1 行で説明する。

        run 全体の内訳は report.md が出す。ここは**止めた連続**だけを見る。
        """
        with self._lock:
            streak = self._streak
            counts = _count_codes(self._streak_error_codes)
        breakdown = ", ".join(f"{code}: {count}" for code, count in counts)
        return f"LLM 呼び出しが {streak} 件連続で失敗した ({breakdown})"


def _count_codes(codes: List[str]) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return sorted(counts.items())

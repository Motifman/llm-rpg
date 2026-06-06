"""TraceRecorder の実装 (Issue #188 Phase 1d)。

呼び出し側は ``ITraceRecorder`` 経由で kind を指定して 1 イベント記録する。
- ``JsonlTraceRecorder``: 指定パスに 1 行ずつ JSON を append。実シナリオで使う
- ``NullTraceRecorder``: 何も記録しない no-op。テストや trace 無効時のデフォルト

呼び出し側責務:
- recorder は context manager として使えるが、明示的に close も可能
- 同一 recorder を複数スレッドで共有する想定はしない (シナリオは単一プロセス
  単一スレッドで回す前提)。
- 例外: 非同期 LLM 主観文付与スケジューラ (#310) は worker thread から
  ``record`` を呼ぶ。``close`` 後の write は close-race として静かに dropped
  され、``record_dropped_after_close`` がカウンタで観測可能 (#311 後続)。
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, TextIO

from ai_rpg_world.application.trace.events import TraceEvent

_logger = logging.getLogger(__name__)


class ITraceRecorder(ABC):
    """シナリオ実行を「人間が振り返れるイベント列」として記録する口。"""

    @abstractmethod
    def record(
        self,
        kind: str,
        *,
        tick: Optional[int] = None,
        player_id: Optional[int] = None,
        **payload: Any,
    ) -> TraceEvent:
        """1 イベント記録し、振った TraceEvent を返す。"""

    @abstractmethod
    def close(self) -> None:
        """背後のリソース (ファイル等) を閉じる。"""

    def __enter__(self) -> "ITraceRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class NullTraceRecorder(ITraceRecorder):
    """記録しない no-op recorder。trace 無効時の既定。"""

    def __init__(self) -> None:
        self._seq = 0
        # PR #358 review HIGH 1 後続: Phase A 並列化 (#354) + 非同期 LLM 主観文
        # scheduler (#309) で複数 thread が同時に record を叩く。_seq の
        # increment は GIL があっても複合代入なので保護する必要がある。
        self._lock = threading.Lock()

    def record(
        self,
        kind: str,
        *,
        tick: Optional[int] = None,
        player_id: Optional[int] = None,
        **payload: Any,
    ) -> TraceEvent:
        with self._lock:
            self._seq += 1
            seq = self._seq
        return TraceEvent(
            seq=seq,
            timestamp=_utc_now_iso(),
            kind=str(kind),
            tick=tick,
            player_id=player_id,
            payload=dict(payload),
        )

    def close(self) -> None:
        # 何もしない
        pass


class JsonlTraceRecorder(ITraceRecorder):
    """JSON Lines ファイルに 1 イベント 1 行で append する recorder。

    path の親ディレクトリは事前に存在している前提 (呼び出し側が用意)。
    """

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be Path")
        self._path = path
        self._fh: Optional[TextIO] = open(path, "w", encoding="utf-8")
        self._seq = 0
        # Issue #311 後続 (#325 結果): 非同期 LLM 主観文付与 scheduler のワーカー
        # thread が close 後に record を呼ぶ "close race" を観測可能にするカウンタ。
        # 値が大きいときは scheduler shutdown drain がタイムアウトしている可能性。
        self._record_dropped_after_close: int = 0
        # PR #358 review HIGH 1 後続: Phase A 並列化 + 非同期 scheduler で複数
        # thread が同時に record を叩くと _seq / _fh.write が interleave して
        # JSONL が破損する。lock で record 全体を直列化する。
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def record_dropped_after_close(self) -> int:
        """``close()`` 後に到着した ``record()`` の件数 (close-race 観測用)。

        # 0 が理想。非同期スケジューラの drain がタイムアウトしていなければ 0 に
        近づく。Viewer / 集計には乗らないが、本番 run 後のログから観測可能。
        """
        return self._record_dropped_after_close

    def record(
        self,
        kind: str,
        *,
        tick: Optional[int] = None,
        player_id: Optional[int] = None,
        **payload: Any,
    ) -> TraceEvent:
        with self._lock:
            if self._fh is None:
                # Issue #311 後続: 非同期 LLM 主観文付与 (#310) のワーカー thread が
                # ``runtime.shutdown(timeout)`` のタイムアウト後に完了した場合、
                # 既に閉じた recorder に書き込みを試みる "close race" が起きる。
                # これは非同期パイプラインで構造的に避けがたいので、例外を投げる
                # 代わりに **silently drop + カウンタ加算** で処理する。
                self._record_dropped_after_close += 1
                _logger.debug(
                    "JsonlTraceRecorder.record(%s) dropped: recorder already closed "
                    "(total dropped=%d)",
                    kind,
                    self._record_dropped_after_close,
                )
                return TraceEvent(
                    seq=-1,
                    timestamp=_utc_now_iso(),
                    kind=str(kind),
                    tick=tick,
                    player_id=player_id,
                    payload=dict(payload),
                )
            self._seq += 1
            event = TraceEvent(
                seq=self._seq,
                timestamp=_utc_now_iso(),
                kind=str(kind),
                tick=tick,
                player_id=player_id,
                payload=dict(payload),
            )
            self._fh.write(json.dumps(event.to_jsonable(), ensure_ascii=False))
            self._fh.write("\n")
            self._fh.flush()
            return event

    def close(self) -> None:
        # close は lock 内で fh を None にすることで record との競合を防ぐ
        # (race: A thread が record の lock を取った直後に close が走り、
        # A 側で _fh is None チェック後の write が NPE になるパスを潰す)。
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
        if self._record_dropped_after_close > 0:
            # 大量に dropped していたら shutdown drain の調整が必要なので
            # INFO で残す。0 件 (= 完璧な drain) では何も出さない。
            _logger.info(
                "JsonlTraceRecorder closed with %d post-close record drops "
                "(async scheduler may need longer shutdown timeout)",
                self._record_dropped_after_close,
            )


def load_trace_events(path: Path) -> Iterable[TraceEvent]:
    """JSONL ファイルから TraceEvent を順次返すジェネレータ (viewer 用)。"""
    if not isinstance(path, Path):
        raise TypeError("path must be Path")
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            yield TraceEvent.from_jsonable(data)


def _utc_now_iso() -> str:
    """`datetime.now(timezone.utc)` を ISO 8601 文字列で返す。"""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ITraceRecorder",
    "JsonlTraceRecorder",
    "NullTraceRecorder",
    "load_trace_events",
]

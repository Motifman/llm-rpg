import sqlite3
import logging
from contextlib import contextmanager
from typing import Iterable, Optional, List


logger = logging.getLogger(__name__)


class Database:
    """
    SQLite 用の薄いユーティリティ。

    - PRAGMA の統一設定（foreign_keys, busy_timeout, journal_mode, synchronous, row_factory）
    - 明示的なトランザクション管理（BEGIN <MODE> ... COMMIT/ROLLBACK）
    - シンプルな execute/query ヘルパー
    """

    def __init__(
        self,
        db_path: str,
        *,
        busy_timeout_ms: int = 5000,
        enable_wal: bool = True,
    ) -> None:
        self.db_path = db_path
        # デフォルトのトランザクション分離（DEFERRED）。明示 BEGIN で制御する。
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

        # 基本PRAGMA
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        try:
            if enable_wal:
                self._conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            # 一部環境で設定できないことがあるため握りつぶす
            pass
        self._conn.execute("PRAGMA synchronous = NORMAL")

        logger.info(f"Database connected: {self.db_path}")

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        try:
            self._conn.close()
        finally:
            logger.info("Database connection closed")

    @contextmanager
    def transaction(self, mode: str = "DEFERRED"):
        """
        トランザクションを開始してスコープを抜けると自動で COMMIT/ROLLBACK する。
        mode: DEFERRED | IMMEDIATE | EXCLUSIVE
        """
        try:
            self._conn.execute(f"BEGIN {mode}")
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def execute(self, sql: str, params: Optional[Iterable] = None) -> sqlite3.Cursor:
        cur = self._conn.cursor()
        cur.execute(sql, tuple(params or ()))
        return cur

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable]) -> sqlite3.Cursor:
        cur = self._conn.cursor()
        cur.executemany(sql, seq_of_params)
        return cur

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def query(self, sql: str, params: Optional[Iterable] = None) -> List[sqlite3.Row]:
        cur = self.execute(sql, params)
        return cur.fetchall()



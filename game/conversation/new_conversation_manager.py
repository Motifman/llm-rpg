import sqlite3
import logging
from game.conversation.new_message import ReceivedMessage, OutgoingMessage
from typing import List, Any

logger = logging.getLogger(__name__)


class ConversationDispatcher:
    """
    メッセージの送信と受信を管理するクラス
    取得したメッセージをデータベースに保存し、送信先を解決して送信する
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        # DB接続とSQLite推奨設定
        self.db_conn = sqlite3.connect(self.db_path)
        # 行アクセスを辞書風に扱えるようにする（将来のSELECTで有用）
        self.db_conn.row_factory = sqlite3.Row
        # 参照整合性を有効化
        self.db_conn.execute("PRAGMA foreign_keys = ON")
        # 書込み競合時の待機時間（ms）
        self.db_conn.execute("PRAGMA busy_timeout = 5000")
        # 同時読み込み性能向上（ファイルDB向け）
        try:
            self.db_conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            # 一部環境で変更できない場合があるため失敗しても続行
            pass
        # 耐障害性と速度のバランス
        self.db_conn.execute("PRAGMA synchronous = NORMAL")

        self.cursor = self.db_conn.cursor()
        logger.info(f"Database connection established successfully to {self.db_path}")
        
        try:
            self._create_table()
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise e
        logger.info(f"ConversationDispatcher initialized with db_path: {self.db_path}")
        
    def _create_table(self):
        try:
            # DDLとインデックスは一括で実行（原子性）
            self.db_conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id   TEXT PRIMARY KEY,
                    sender_id    TEXT NOT NULL,
                    spot_id      TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    audience_kind TEXT NOT NULL,
                    shout_level  INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_audiences (
                    message_id   TEXT NOT NULL,
                    audience_id  TEXT NOT NULL,
                    PRIMARY KEY (message_id, audience_id),
                    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS message_recipients (
                    message_id    TEXT NOT NULL,
                    recipient_id  TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    delivered_at  TEXT,
                    read_at       TEXT,
                    created_at    TEXT NOT NULL,
                    PRIMARY KEY (message_id, recipient_id),
                    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
                    CHECK (status IN ('pending','delivered','read'))
                );

                CREATE INDEX IF NOT EXISTS idx_message_audiences_msg
                ON message_audiences(message_id);

                CREATE INDEX IF NOT EXISTS idx_message_recipients_msg
                ON message_recipients(message_id);

                CREATE INDEX IF NOT EXISTS idx_inbox
                ON message_recipients(recipient_id, status, created_at);
                """
            )
            self.db_conn.commit()
            logger.info(f"ConversationDispatcher tables and indexes created")
        except Exception as e:
            logger.error(f"Failed to create table or indexes: {e}")
            self.db_conn.rollback()
            raise e
    
    def __del__(self):
        if self.db_conn:
            self.db_conn.close()
            logger.info(f"Database connection closed")

    def speak(self, message: OutgoingMessage):
        pass
        
    def dispatch(self, message: Any):
        pass
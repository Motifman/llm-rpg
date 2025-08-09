import sqlite3
import logging
import uuid
import datetime
from typing import List
from game.core.database import Database
from game.conversation.new_message import OutgoingMessage, DeliveryStatus, ReceivedMessage

logger = logging.getLogger(__name__)


class ConversationDispatcher:
    """
    メッセージの送信と受信を管理するクラス
    取得したメッセージをデータベースに保存し、送信先を解決して送信する
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = Database(self.db_path)
        self.db_conn = self.db.conn
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
            self.db_conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id   TEXT PRIMARY KEY,
                    sender_id    TEXT NOT NULL,
                    spot_id      TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    audience_kind TEXT NOT NULL,
                    is_shout     BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at   TEXT NOT NULL,
                    CHECK (audience_kind IN ('spot_all','players'))
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
        if getattr(self, "db", None):
            self.db.close()

    def speak(self, message: OutgoingMessage) -> str:
        message_id = str(uuid.uuid4())
        self.cursor.execute(
            """
            INSERT INTO messages (message_id, sender_id, spot_id, content, audience_kind, is_shout, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                message.sender_id,
                message.spot_id,
                message.content,
                message.audience_kind.value,
                message.is_shout,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
        for audience_id in message.audience_ids:
            self.cursor.execute(
                """
                INSERT INTO message_recipients (message_id, recipient_id, status, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    message_id,
                    audience_id,
                    DeliveryStatus.PENDING.value,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )
        self.db_conn.commit()
        return message_id

    def dispatch(self, player_id: str) -> List[ReceivedMessage]:
        """
        プレイヤーが未読のメッセージを取得する
        """
        try:
            # 競合を避けるため、取得〜既読反映を同一トランザクションで行う
            with self.db.transaction("IMMEDIATE"):
                self.cursor.execute(
                    """
                    SELECT mr.message_id, m.sender_id, m.spot_id, m.content, m.audience_kind, m.is_shout
                    FROM message_recipients mr
                    JOIN messages m ON mr.message_id = m.message_id
                    WHERE mr.recipient_id = ? AND mr.status = ?
                    """,
                    (player_id, DeliveryStatus.PENDING.value),
                )
                rows = self.cursor.fetchall()

                if not rows:
                    return []

                message_ids = [row["message_id"] for row in rows]
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()

                placeholders = ",".join(["?"] * len(message_ids))
                params = [
                    DeliveryStatus.READ.value,
                    now,
                    player_id,
                    DeliveryStatus.PENDING.value,
                    *message_ids,
                ]

                self.cursor.execute(
                    f"""
                    UPDATE message_recipients
                    SET status = ?, read_at = ?
                    WHERE recipient_id = ? AND status = ? AND message_id IN ({placeholders})
                    """,
                    params,
                )

                return [ReceivedMessage(**row) for row in rows]
        except Exception:
            raise
            
    def clear_read_messages(self, player_id: str):
        with self.db.transaction("IMMEDIATE"):
            self.cursor.execute(
                """
                DELETE FROM message_recipients
                WHERE recipient_id = ? AND status = ?
                """,
                (player_id, DeliveryStatus.READ.value),
            )
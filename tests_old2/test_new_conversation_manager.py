import os
import sqlite3
import uuid

import pytest

from game.conversation.new_conversation_manager import ConversationDispatcher
from game.conversation.new_message import OutgoingMessage, AudienceKind, DeliveryStatus


@pytest.fixture()
def db_path(tmp_path) -> str:
    # 一時ファイルとしてSQLite DBを作成
    return str(tmp_path / "test_conversation.sqlite3")


def test_dispatch_returns_empty_when_no_messages(db_path: str):
    dispatcher = ConversationDispatcher(db_path)
    messages = dispatcher.dispatch(player_id="player-1")
    assert messages == []


def test_speak_and_dispatch_marks_read(db_path: str):
    dispatcher = ConversationDispatcher(db_path)

    sender_id = "sender-1"
    spot_id = "spot-1"
    player_id = "player-1"

    msg = OutgoingMessage(
        sender_id=sender_id,
        spot_id=spot_id,
        content="hello",
        audience_kind=AudienceKind.PLAYERS,
        audience_ids=[player_id],
        is_shout=False,
    )

    message_id = dispatcher.speak(msg)

    # 取得時に既読化される
    received = dispatcher.dispatch(player_id=player_id)
    assert len(received) == 1
    r = received[0]
    assert r.message_id == message_id
    assert r.sender_id == sender_id
    assert r.spot_id == spot_id
    assert r.content == "hello"

    # DB上でstatus=read, read_atが設定されていること
    cur = dispatcher.db_conn.cursor()
    cur.execute(
        """
        SELECT status, read_at FROM message_recipients
        WHERE message_id = ? AND recipient_id = ?
        """,
        (message_id, player_id),
    )
    row = cur.fetchone()
    assert row is not None
    assert row["status"] == DeliveryStatus.READ.value
    assert row["read_at"] is not None


def test_dispatch_is_idempotent_across_instances(db_path: str):
    d1 = ConversationDispatcher(db_path)
    d2 = ConversationDispatcher(db_path)

    player_id = "player-1"
    msg = OutgoingMessage(
        sender_id="sender-1",
        spot_id="spot-1",
        content="hi",
        audience_kind=AudienceKind.PLAYERS,
        audience_ids=[player_id],
    )
    d1.speak(msg)

    first = d1.dispatch(player_id)
    assert len(first) == 1

    # 既読化済みのため、別インスタンスでも取得できない
    second = d2.dispatch(player_id)
    assert second == []


def test_clear_read_messages_removes_recipient_rows(db_path: str):
    dispatcher = ConversationDispatcher(db_path)

    player_id = "player-1"
    msg = OutgoingMessage(
        sender_id="sender-1",
        spot_id="spot-1",
        content="bye",
        audience_kind=AudienceKind.PLAYERS,
        audience_ids=[player_id],
    )
    message_id = dispatcher.speak(msg)

    # 既読化
    _ = dispatcher.dispatch(player_id)

    # 受信者行の削除
    dispatcher.clear_read_messages(player_id)

    cur = dispatcher.db_conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS cnt FROM message_recipients
        WHERE recipient_id = ?
        """,
        (player_id,),
    )
    cnt = cur.fetchone()["cnt"]
    assert cnt == 0



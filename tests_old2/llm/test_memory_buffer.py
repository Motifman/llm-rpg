from datetime import datetime, timezone

from game.llm.memory import (
    FixedLengthMessageBuffer,
    PlayerMemoryStore,
    ObservationMessage,
    ActionMessage,
    OutcomeMessage,
)


def _msg(content: str, tokens: int = 1):
    m = ObservationMessage(content=content)
    m.tokens_estimate = tokens
    m.timestamp = datetime.now(timezone.utc)
    return m


def test_fixed_length_ring_behavior():
    buf = FixedLengthMessageBuffer(maxlen=3)
    buf.append(_msg("m1"))
    buf.append(_msg("m2"))
    buf.append(_msg("m3"))
    buf.append(_msg("m4"))  # m1 が追い出される

    all_msgs = buf.get_all()
    assert len(all_msgs) == 3
    assert [m.content for m in all_msgs] == ["m2", "m3", "m4"]


def test_get_recent_order_and_limit():
    buf = FixedLengthMessageBuffer(maxlen=5)
    for i in range(1, 6):
        buf.append(_msg(f"m{i}"))

    recent = buf.get_recent(limit=2)
    assert [m.content for m in recent] == ["m4", "m5"]


def test_get_for_token_budget():
    buf = FixedLengthMessageBuffer(maxlen=10)
    # 合計トークン= 1+2+3+4 = 10
    buf.append(_msg("a", tokens=1))
    buf.append(_msg("b", tokens=2))
    buf.append(_msg("c", tokens=3))
    buf.append(_msg("d", tokens=4))

    # 予算=5 -> 直近から d(4) は入るが、次に c(3) を追加すると 7>5 なので d のみ
    sub = buf.get_for_token_budget(token_budget=5)
    assert [m.content for m in sub] == ["d"]

    # 予算=9 -> d(4)+c(3)=7 まで入り、次の b(2) を追加すると 9 で丁度
    sub2 = buf.get_for_token_budget(token_budget=9)
    assert [m.content for m in sub2] == ["b", "c", "d"]


def test_player_memory_store_basic():
    store = PlayerMemoryStore(default_maxlen=3)
    pid = "player-1"
    store.append(pid, _msg("x1"))
    store.append(pid, _msg("x2"))
    store.append(pid, _msg("x3"))
    store.append(pid, _msg("x4"))

    recent = store.get_recent(pid)
    assert [m.content for m in recent] == ["x2", "x3", "x4"]

    budget = store.get_for_token_budget(pid, token_budget=2)
    # 直近から x4(1) は入り、次に x3(1) を加えて 2 まで
    for m in budget:
        m.tokens_estimate = 1  # 念のため固定
    assert [m.content for m in budget] == ["x3", "x4"]



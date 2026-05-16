"""``IntentIdGenerator`` の単調増加と排他制御の単体テスト。"""

import threading

import pytest

from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)


class TestIntentIdGenerator:
    """``IntentIdGenerator`` の発行挙動。"""

    def test_starts_at_one_by_default(self) -> None:
        """既定では 1 から払い出される。"""
        gen = IntentIdGenerator()
        assert gen.next_id().value == 1

    def test_monotonically_increases(self) -> None:
        """連続呼び出しで単調増加する。"""
        gen = IntentIdGenerator()
        ids = [gen.next_id().value for _ in range(5)]
        assert ids == [1, 2, 3, 4, 5]

    def test_custom_start_value(self) -> None:
        """start で開始点を指定できる。"""
        gen = IntentIdGenerator(start=100)
        assert gen.next_id().value == 100
        assert gen.next_id().value == 101

    def test_negative_start_rejected(self) -> None:
        """負の start は弾く。"""
        with pytest.raises(ValueError):
            IntentIdGenerator(start=-1)

    def test_thread_safety_no_duplicate_ids(self) -> None:
        """スレッド競合下でも重複 ID は発行されない (Lock の保証)。"""
        gen = IntentIdGenerator()
        collected: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            for _ in range(200):
                v = gen.next_id().value
                with lock:
                    collected.append(v)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(collected) == 8 * 200
        assert len(set(collected)) == 8 * 200

"""
``_WorldLlmTurnTrigger`` の self-reschedule streak の挙動を保証する。

旧名: ``max_turns`` / ``_turn_counts``。実体は「TRPG のターン」ではなく
**「自己 reschedule (= should_reschedule=True) の連続チェインを上限で
打ち切る」** ためのカウンタなので、PR-I で意味を反映した名前に変更した。

責務:
- self-reschedule chain (= 自分の result.should_reschedule=True で繰り返し
  起床する自走ループ) の連続数を ``max_self_reschedule_streak`` で打ち切る
- 他者観測 / 失敗通知 / arrival callback 等の **外部起床** (= schedule_turn
  経由) は streak を**触らない** → ping-pong は永続して良い (= 自然な
  相互作用)
- ``was_no_op`` や ``should_reschedule=False`` の result は chain を終了させて
  streak を消去する
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _WorldLlmTurnTrigger,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass
class _ResultStub:
    """``LlmCommandResultDto`` の最小スタブ。_account_result が必要なフィールドだけ。"""
    should_reschedule: bool = False
    was_no_op: bool = False


def _make_trigger(max_streak: int = 5) -> _WorldLlmTurnTrigger:
    """wiring を None でも動かせる最小スタブ trigger を組み立てる。

    _account_result は wiring に触らないので、wiring=None で十分。
    """

    class _DummyRuntime:
        """_note_activity_after_turn / _note_turn_for_reinterpretation が
        参照する runtime の最小スタブ。"""
        _episodic_stack = None  # _note_turn_for_reinterpretation 用
        # _note_activity_after_turn は idle_timer attribute を見るだけ

    class _DummyWiring:
        runtime = _DummyRuntime()

    return _WorldLlmTurnTrigger(
        wiring=_DummyWiring(),
        max_self_reschedule_streak=max_streak,
    )


def _pid(value: int) -> PlayerId:
    return PlayerId(value)


class TestSelfRescheduleStreakIncrement:
    """should_reschedule=True を返す result は streak を +1 し、pending に戻す。"""

    def test_first_self_reschedule_makes_streak_1(self):
        """初回 should_reschedule=True で streak が 0 → 1 になる。"""
        t = _make_trigger()
        t._account_result(1, _ResultStub(should_reschedule=True))
        assert t._self_reschedule_streak.get(1) == 1
        assert 1 in t.pending_player_ids

    def test_repeated_self_reschedules_accumulate(self):
        """連続 should_reschedule=True で streak が 1, 2, 3, ... と増える。"""
        t = _make_trigger()
        for expected in (1, 2, 3, 4):
            t._account_result(1, _ResultStub(should_reschedule=True))
            assert t._self_reschedule_streak.get(1) == expected


class TestSelfRescheduleStreakLimit:
    """streak が max に達したら pending には追加されない (= self-loop stop)。"""

    def test_streak_at_max_pops_streak(self):
        """max_self_reschedule_streak=3 のとき、3 回目で chain 強制終了 (= streak が
        pop される)。pending には触らない (= 外部起床経由の追加を消さない)。"""
        t = _make_trigger(max_streak=3)
        for _ in range(3):
            t._account_result(1, _ResultStub(should_reschedule=True))
        # streak は pop される (= 次回 fresh start)
        assert 1 not in t._self_reschedule_streak

    def test_streak_at_max_does_not_touch_pending(self):
        """max 到達時に pending を直接 discard しない。外部観測経由で同 wave 内
        に schedule_turn(pid) が来ていた場合に、その起床を妨げないため。"""
        t = _make_trigger(max_streak=3)
        # 外部観測経由の起床を simulate
        t.schedule_turn(_pid(1))
        assert 1 in t.pending_player_ids
        # 3 回目の self-reschedule で max 到達 → streak pop。pending は触らない
        for _ in range(3):
            t._account_result(1, _ResultStub(should_reschedule=True))
        # streak は pop されたが、外部起床経由の pending 登録は残る
        assert 1 not in t._self_reschedule_streak
        assert 1 in t.pending_player_ids

    def test_streak_just_under_max_keeps_chain(self):
        """max_self_reschedule_streak=3 のとき、2 回目までは streak が残り pending
        に居続ける (= chain 継続)。"""
        t = _make_trigger(max_streak=3)
        for _ in range(2):
            t._account_result(1, _ResultStub(should_reschedule=True))
        assert t._self_reschedule_streak.get(1) == 2
        assert 1 in t.pending_player_ids


class TestSelfRescheduleStreakReset:
    """chain を終了させるイベントで streak が消去される。"""

    def test_was_no_op_clears_streak(self):
        """was_no_op=True で streak が pop される。"""
        t = _make_trigger()
        t._account_result(1, _ResultStub(should_reschedule=True))
        t._account_result(1, _ResultStub(was_no_op=True))
        assert 1 not in t._self_reschedule_streak

    def test_normal_success_clears_streak(self):
        """should_reschedule=False かつ was_no_op=False (= 通常成功 or 失敗だが
        reschedule 不要) で streak が pop される。"""
        t = _make_trigger()
        t._account_result(1, _ResultStub(should_reschedule=True))
        t._account_result(1, _ResultStub(should_reschedule=False))
        assert 1 not in t._self_reschedule_streak


class TestScheduleTurnDoesNotTouchStreak:
    """外部起床 (= schedule_turn) は streak に介入しない (= ping-pong は自然)。"""

    def test_schedule_turn_does_not_increment_streak(self):
        """schedule_turn を 100 回呼んでも streak は 0 のまま。"""
        t = _make_trigger()
        for _ in range(100):
            t.schedule_turn(_pid(1))
        assert t._self_reschedule_streak.get(1, 0) == 0
        assert 1 in t.pending_player_ids

    def test_schedule_turn_does_not_reset_existing_streak(self):
        """self-reschedule で streak=3 の状態に schedule_turn が来ても streak は
        保持される (= 旧 setdefault と同等の挙動を保つ)。"""
        t = _make_trigger()
        for _ in range(3):
            t._account_result(1, _ResultStub(should_reschedule=True))
        assert t._self_reschedule_streak[1] == 3
        t.schedule_turn(_pid(1))
        assert t._self_reschedule_streak[1] == 3

    def test_ping_pong_does_not_block(self):
        """A↔B の ping-pong (= 互いに schedule_turn で起こし合う) が
        streak の制限を受けないこと。"""
        t = _make_trigger(max_streak=3)
        # 10 回 ping-pong しても streak は 0 のまま、両者 pending に残る
        for _ in range(10):
            t.schedule_turn(_pid(1))
            t.schedule_turn(_pid(2))
            # 各 wave で should_reschedule=False の通常 turn として決算
            t._account_result(1, _ResultStub(should_reschedule=False))
            t._account_result(2, _ResultStub(should_reschedule=False))
        assert t._self_reschedule_streak.get(1, 0) == 0
        assert t._self_reschedule_streak.get(2, 0) == 0


class TestSelfLoopVsExternalWakeUpMix:
    """自己 reschedule と外部起床が混ざるケースの境界挙動。"""

    def test_self_reschedule_after_max_starts_fresh_chain(self):
        """self-loop で max に達して streak が pop された後、次の self-reschedule は
        streak=1 から数え直す (= fresh start)。soft cap として機能する。"""
        t = _make_trigger(max_streak=3)
        # 3 回目で max に到達 → streak pop
        for _ in range(3):
            t._account_result(1, _ResultStub(should_reschedule=True))
        assert 1 not in t._self_reschedule_streak
        # 次の self-reschedule は streak=1 から
        t._account_result(1, _ResultStub(should_reschedule=True))
        assert t._self_reschedule_streak[1] == 1

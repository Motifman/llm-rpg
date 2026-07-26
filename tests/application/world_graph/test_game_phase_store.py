"""世界全体のモード (自由時間 / 会議) を、排他が壊れない形で持てることを保証する。

設計 doc (docs/memory_system/meeting_and_voting_design.md §2.1) の PR 1。

`world_flag` に `phase:meeting` のようなフラグを立てる案を採らなかったのは、
フラグでは排他を型が保証できないため。`phase:meeting` と `phase:free` が
同時に立った状態を止められず、「会議が終わったのに消し忘れて永久に会議」が
静かに起きる。

ここでは **現在のフェーズが常にちょうど 1 つ**であることを、遷移メソッドの
形で保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GamePhaseTransitionException,
)
from ai_rpg_world.domain.world_graph.value_object.game_phase_state import (
    GamePhaseState,
)


class TestInitialState:
    """世界は自由時間から始まる。"""

    def test_starts_in_free_roam(self) -> None:
        """初期フェーズは FREE_ROAM。"""
        assert GamePhaseStore().current.phase is GamePhase.FREE_ROAM

    def test_initial_state_has_no_trigger(self) -> None:
        """初期状態には招集理由が無い (誰かが始めたわけではない)。"""
        assert GamePhaseStore().current.trigger is None

    def test_initial_tick_is_recorded(self) -> None:
        """開始 tick が記録される (経過を測る起点になる)。"""
        store = GamePhaseStore(initial_tick=7)
        assert store.current.started_at_tick == 7


class TestBeginMeeting:
    """招集で会議へ移る。"""

    def test_phase_becomes_meeting(self) -> None:
        """begin_meeting でフェーズが MEETING になる。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        assert store.current.phase is GamePhase.MEETING

    def test_trigger_is_recorded(self) -> None:
        """何がきっかけで会議になったかが残る。

        緊急ボタンと死体発見では、その後の議論の意味が変わる。分析でも
        区別したい。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="body_report")
        assert store.current.trigger == "body_report"

    def test_started_tick_is_the_transition_tick(self) -> None:
        """開始 tick は遷移した tick になる (会議の tick 上限の起点)。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        assert store.current.started_at_tick == 10

    def test_activity_starts_at_the_transition_tick(self) -> None:
        """最終活動 tick も遷移時に初期化される。

        ここを 0 のままにすると、会議が始まった瞬間に沈黙上限を超えて
        即終了する。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        assert store.current.last_activity_tick == 10


class TestExclusivity:
    """同時に 2 つのフェーズには入れない。"""

    def test_beginning_a_meeting_twice_is_rejected(self) -> None:
        """会議中にもう一度招集すると例外になる。

        1 tick 内で全プレイヤーが並列に行動するので、2 人が同じ tick に
        緊急ボタンを押すことは実際に起こりうる。黙って 2 回目を通すと
        開始 tick が上書きされ、会議の tick 上限が伸び続ける。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")

        with pytest.raises(GamePhaseTransitionException):
            store.begin_meeting(tick=10, trigger="body_report")

    def test_the_first_meeting_survives_the_rejected_second(self) -> None:
        """拒否された 2 回目は、進行中の会議を壊さない。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")

        with pytest.raises(GamePhaseTransitionException):
            store.begin_meeting(tick=12, trigger="body_report")

        assert store.current.started_at_tick == 10
        assert store.current.trigger == "emergency_button"

    def test_ending_without_a_meeting_is_rejected(self) -> None:
        """自由時間で会議を終わらせようとすると例外になる。"""
        store = GamePhaseStore()

        with pytest.raises(GamePhaseTransitionException):
            store.end_meeting(tick=10, reason="vote_concluded")


class TestEndMeeting:
    """会議は必ず自由時間へ戻る。"""

    def test_phase_returns_to_free_roam(self) -> None:
        """end_meeting で FREE_ROAM に戻る。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")
        assert store.current.phase is GamePhase.FREE_ROAM

    def test_end_reason_is_recorded_as_the_next_trigger(self) -> None:
        """なぜ会議が終わったかが残る。

        投票で決着したのか、沈黙で流れたのか、時間切れかは、分析で
        区別したい (会議が機能しているかの指標になる)。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="silence")
        assert store.current.trigger == "silence"

    def test_a_new_meeting_can_start_after_ending(self) -> None:
        """終わった後はまた招集できる。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")
        store.begin_meeting(tick=40, trigger="body_report")
        assert store.current.phase is GamePhase.MEETING


class TestActivityTracking:
    """沈黙上限を測るための最終活動 tick。"""

    def test_note_activity_moves_the_marker(self) -> None:
        """発言があれば最終活動 tick が進む。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.note_activity(tick=15)
        assert store.current.last_activity_tick == 15

    def test_silence_is_measured_from_the_last_activity(self) -> None:
        """沈黙の長さは最終活動からの経過で測る。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.note_activity(tick=15)
        assert store.ticks_since_activity(tick=18) == 3

    def test_older_activity_does_not_rewind_the_marker(self) -> None:
        """過去 tick の活動報告でマーカーは巻き戻らない。

        1 tick 内の並列処理で報告順が前後しうる。巻き戻すと沈黙判定が
        伸び、会議が終わらなくなる。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.note_activity(tick=15)
        store.note_activity(tick=12)
        assert store.current.last_activity_tick == 15


class TestHistory:
    """遷移の履歴を残す (trace と分析用)。"""

    def test_transitions_are_recorded_in_order(self) -> None:
        """遷移が起きた順に積まれる。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")

        phases = [entry.phase for entry in store.history]

        assert phases == [GamePhase.FREE_ROAM, GamePhase.MEETING, GamePhase.FREE_ROAM]

    def test_history_is_capped(self) -> None:
        """履歴は上限で頭から捨てる。

        長走 run で無限に伸びると snapshot が膨らみ続ける。直近の遷移だけ
        あれば分析には足りる。
        """
        store = GamePhaseStore()
        for tick in range(0, GamePhaseStore.MAX_HISTORY * 4, 2):
            store.begin_meeting(tick=tick, trigger="emergency_button")
            store.end_meeting(tick=tick + 1, reason="silence")

        assert len(store.history) == GamePhaseStore.MAX_HISTORY

    def test_activity_updates_do_not_grow_the_history(self) -> None:
        """発言のたびに履歴が伸びたりしない (遷移だけを記録する)。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        before = len(store.history)
        for tick in range(11, 30):
            store.note_activity(tick=tick)
        assert len(store.history) == before


class TestStateValidation:
    """状態そのものの不整合は構築時に弾く。"""

    def test_negative_tick_is_rejected(self) -> None:
        """負の tick はありえない。"""
        with pytest.raises(GamePhaseTransitionException):
            GamePhaseState(
                phase=GamePhase.FREE_ROAM,
                started_at_tick=-1,
                last_activity_tick=-1,
            )

    def test_activity_before_start_is_rejected(self) -> None:
        """最終活動が開始より前にはなりえない。

        ここが崩れると沈黙の経過が負になり、会議が永久に終わらない。
        """
        with pytest.raises(GamePhaseTransitionException):
            GamePhaseState(
                phase=GamePhase.MEETING,
                started_at_tick=10,
                last_activity_tick=5,
            )

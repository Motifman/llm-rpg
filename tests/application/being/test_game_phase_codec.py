"""会議の途中で snapshot を取って再開しても、会議が続くことを保証する。

フェーズを保存しないと、再開した世界は必ず自由時間から始まる。しかも
「会議中に落ちた」と「会議が終わってから落ちた」が区別できないので、
再開したデータを見ても異常に気付けない。

開始 tick と最終活動 tick を保存するのも同じ理由である。これを derive
できると思って落とすと、**再開のたびに会議の tick 上限と沈黙上限の起点が
リセットされ、会議が延びる**。再現性のある実験にならない。

store を足す PR で codec も同時に入れる方針は per-Being store の checklist
(`design_decisions.md` #27) と同じ。「あとで足す」と長走実験の終了 → 再開で
連続性が静かに壊れる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.world_subsystems.game_phase_codec import (
    SCHEMA_VERSION,
    GamePhaseSubsystemCodec,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase


class _StubRuntime:
    def __init__(self, store: GamePhaseStore | None) -> None:
        self._game_phase_store = store


def _round_trip(store: GamePhaseStore) -> GamePhaseStore:
    """capture した内容を、まっさらな store へ restore して返す。"""
    codec = GamePhaseSubsystemCodec()
    payload = codec.capture(_StubRuntime(store))
    restored = GamePhaseStore()
    codec.restore(_StubRuntime(restored), payload)
    return restored


class TestMidMeetingRoundTrip:
    """会議中の状態がそのまま戻る。"""

    def test_phase_survives(self, ) -> None:
        """再開しても会議が続いている。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="body_report")

        assert _round_trip(store).current.phase is GamePhase.MEETING

    def test_started_tick_survives(self) -> None:
        """会議の開始 tick が戻る (tick 上限の起点)。

        落とすと再開のたびに会議が延びる。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="body_report")

        assert _round_trip(store).current.started_at_tick == 10

    def test_last_activity_survives(self) -> None:
        """最終活動 tick が戻る (沈黙上限の起点)。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="body_report")
        store.note_activity(tick=17)

        assert _round_trip(store).current.last_activity_tick == 17

    def test_trigger_survives(self) -> None:
        """招集のきっかけが戻る (分析で緊急ボタンと死体発見を区別する)。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="body_report")

        assert _round_trip(store).current.trigger == "body_report"

    def test_history_survives(self) -> None:
        """遷移履歴が戻る。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")
        store.begin_meeting(tick=40, trigger="body_report")

        restored = _round_trip(store)

        assert [entry.phase for entry in restored.history] == [
            GamePhase.FREE_ROAM,
            GamePhase.MEETING,
            GamePhase.FREE_ROAM,
            GamePhase.MEETING,
        ]


class TestRestoreReplacesRatherThanAppends:
    """復元は置換であって追記ではない。"""

    def test_history_is_not_accumulated_across_restores(self) -> None:
        """再開のたびに履歴が積み増されない。

        追記になっていると、長走 run を何度も再開するうちに履歴が膨らみ、
        「何回会議があったか」の分析も狂う。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        codec = GamePhaseSubsystemCodec()
        payload = codec.capture(_StubRuntime(store))

        target = GamePhaseStore()
        target.begin_meeting(tick=99, trigger="body_report")
        target.end_meeting(tick=100, reason="silence")
        codec.restore(_StubRuntime(target), payload)

        assert len(target.history) == len(store.history)
        assert target.current.started_at_tick == 10


class TestFailureModes:
    """壊れた payload は黙って無視しない。"""

    def test_unknown_schema_version_raises(self) -> None:
        """未知の schema_version は例外にする。"""
        codec = GamePhaseSubsystemCodec()
        with pytest.raises(ValueError):
            codec.restore(
                _StubRuntime(GamePhaseStore()),
                {"schema_version": SCHEMA_VERSION + 99, "current": None},
            )

    def test_unknown_phase_value_raises(self) -> None:
        """未知のフェーズ名は例外にする。

        黙って FREE_ROAM に倒すと、会議中に取った snapshot が自由時間として
        再開され、しかもそれに気付けない。
        """
        codec = GamePhaseSubsystemCodec()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "current": {
                "phase": "VOTING",
                "started_at_tick": 1,
                "last_activity_tick": 1,
                "trigger": None,
            },
            "history": [],
        }
        with pytest.raises(ValueError):
            codec.restore(_StubRuntime(GamePhaseStore()), payload)

    def test_runtime_without_a_store_is_left_alone(self) -> None:
        """store を持たない runtime では何もしない (落ちない)。"""
        codec = GamePhaseSubsystemCodec()
        payload = codec.capture(_StubRuntime(None))
        codec.restore(_StubRuntime(None), payload)  # 例外が出ないこと
        assert payload["current"] is None


class TestTriggerLimitsSurviveRestore:
    """招集の制限も再開後に残る。

    落とすと、再開のたびに全員の緊急ボタンが復活し、同じ死体をまた報告
    できてしまう。**回数制限は「持ち札を切る判断」を作るためのもの**なので、
    再開で戻ると判断そのものが無意味になる。
    """

    def test_used_emergency_buttons_survive(self) -> None:
        """使い切ったボタンが復活しない。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        store = GamePhaseStore()
        store.consume_emergency_button(PlayerId(2))

        assert _round_trip(store).has_emergency_button(PlayerId(2)) is False

    def test_unused_buttons_stay_available(self) -> None:
        """使っていない人のボタンは残る。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        store = GamePhaseStore()
        store.consume_emergency_button(PlayerId(2))

        assert _round_trip(store).has_emergency_button(PlayerId(3)) is True

    def test_reported_bodies_survive(self) -> None:
        """報告済みの死体が未報告に戻らない。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        store = GamePhaseStore()
        store.mark_body_reported(PlayerId(4))

        assert _round_trip(store).is_body_reported(PlayerId(4)) is True

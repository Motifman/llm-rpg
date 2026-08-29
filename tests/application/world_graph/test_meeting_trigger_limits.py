"""招集の回数制限とクールダウンを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md §6.3) の PR 4。

## 2 段の制限を別々に持つ理由

| 制限 | 目的 | 既定 |
|---|---|---|
| 個人の使用回数 | 持ち札を切る判断を作る | 1 回 |
| 世界共通クールダウン | 会議直後の再招集を防ぐ | 会議終了から 20 tick |

**個人の使用回数が 1 回なら、個人単位のクールダウンは一度も発動しない**
(2 回目が無いので)。連続招集を防ぐ役目は世界共通のクールダウンが持つ。
目的が別なので別々に持つ。

死体発見による招集はクールダウンの対象外にする。死体は世界の事実であって、
招集の濫用ではない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_A, _B = PlayerId(1), PlayerId(2)


class TestEmergencyButtonUsageIsPerPerson:
    """緊急ボタンは 1 人 1 回。"""

    def test_unused_button_is_available(self) -> None:
        """まだ押していない人は押せる。"""
        assert GamePhaseStore().has_emergency_button(_A) is True

    def test_using_it_consumes_the_card(self) -> None:
        """一度押すと、その人はもう押せない。"""
        store = GamePhaseStore()
        store.consume_emergency_button(_A)
        assert store.has_emergency_button(_A) is False

    def test_other_players_keep_theirs(self) -> None:
        """他の人の持ち札は減らない。

        誰が持ち札を切ったかが情報になるので、共有カウンタにしてはいけない。
        """
        store = GamePhaseStore()
        store.consume_emergency_button(_A)
        assert store.has_emergency_button(_B) is True


class TestWorldCooldown:
    """会議直後の再招集を世界共通で止める。"""

    def test_no_cooldown_before_any_meeting(self) -> None:
        """一度も会議が無ければクールダウンは無い。"""
        assert GamePhaseStore().is_meeting_on_cooldown(tick=0) is False

    def test_cooldown_applies_right_after_a_meeting(self) -> None:
        """会議が終わった直後は招集できない。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")

        assert store.is_meeting_on_cooldown(tick=21) is True

    def test_cooldown_expires(self) -> None:
        """既定 tick 経てば また招集できる。"""
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=20, reason="vote_concluded")

        assert (
            store.is_meeting_on_cooldown(
                tick=20 + GamePhaseStore.DEFAULT_MEETING_COOLDOWN_TICKS
            )
            is False
        )

    def test_cooldown_is_measured_from_the_end_not_the_start(self) -> None:
        """起点は会議の**終わり**であって始まりではない。

        始まりから測ると、長引いた会議ほど次の招集が早く解禁される。
        """
        store = GamePhaseStore()
        store.begin_meeting(tick=10, trigger="emergency_button")
        store.end_meeting(tick=100, reason="tick_limit")

        assert store.is_meeting_on_cooldown(tick=101) is True


class TestBodyReportsAreOncePerBody:
    """同じ死体は 1 度しか報告できない。"""

    def test_first_report_is_allowed(self) -> None:
        """まだ報告されていない相手は報告できる。"""
        assert GamePhaseStore().is_body_reported(_B) is False

    def test_second_report_of_the_same_body_is_blocked(self) -> None:
        """同じ相手を二度は報告できない。

        塞がないと、同じ死体で何度でも会議を開けてしまう。
        """
        store = GamePhaseStore()
        store.mark_body_reported(_B)
        assert store.is_body_reported(_B) is True

    def test_a_different_body_is_still_reportable(self) -> None:
        """別の相手は独立して報告できる。"""
        store = GamePhaseStore()
        store.mark_body_reported(_B)
        assert store.is_body_reported(_A) is False


class TestSnapshotRoundTrip:
    """制限の状態も再開後に残る。"""

    def test_replace_all_carries_the_limits(self) -> None:
        """replace_all で使用済みボタンと報告済み死体も置き換わる。

        残らないと、再開のたびに全員の持ち札が復活し、同じ死体をまた
        報告できてしまう。
        """
        source = GamePhaseStore()
        source.consume_emergency_button(_A)
        source.mark_body_reported(_B)

        target = GamePhaseStore()
        target.replace_all(
            current=source.current,
            history=source.history,
            used_emergency_buttons=source.used_emergency_buttons,
            reported_bodies=source.reported_bodies,
        )

        assert target.has_emergency_button(_A) is False
        assert target.is_body_reported(_B) is True

    def test_rollback_snapshot_restores_ballots_and_reusable_button_storage(
        self,
    ) -> None:
        """rollback復元は票を戻し、その後も緊急ボタンを通常どおり消費できる。"""
        store = GamePhaseStore(emergency_buttons_per_player=2)
        store.cast_vote(_A, _B)
        snapshot = store.rollback_snapshot()
        store.consume_emergency_button(_A)
        store.begin_meeting(tick=1, trigger="emergency_button")

        store.restore_rollback_snapshot(snapshot)
        store.consume_emergency_button(_A)

        assert store.ballots == {int(_A): int(_B)}
        assert store.has_emergency_button(_A) is True

"""UnifiedRecentEventStore が、未処理の観測と直近の行動の結果だけを持ち、足した出来事を聞き手に知らせることを保証する (design_decisions D1824-24)。"""

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    RECENT_ACTION_RESULTS_KEPT,
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PLAYER = PlayerId(7)
_BASE = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _observation(minutes: int, prose: str) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_BASE + timedelta(minutes=minutes),
        game_time_label=f"深夜 0:{minutes:02d}",
        output=ObservationOutput(prose=prose, structured={}),
    )


def _action(minutes: int, summary: str) -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=_BASE + timedelta(minutes=minutes),
        game_time_label=f"深夜 0:{minutes:02d}",
        action_summary=summary,
        result_summary="成功した。",
    )


class TestRecentActionResults:
    """直近の行動の結果を、新しい順に、決まった件数まで持つことを保証する。"""

    def test_recent_action_results_are_newest_first(self) -> None:
        """行動の結果は、起きた時刻の新しい順に limit 件まで返す。"""
        store = UnifiedRecentEventStore()
        for minute, summary in ((1, "扉を開けた"), (3, "階段を降りた"), (2, "棚を調べた")):
            store.append_action_result(_PLAYER, _action(minute, summary))

        assert [e.action_summary for e in store.get_recent_action_results(_PLAYER, 2)] == ["階段を降りた", "棚を調べた"]

    def test_same_time_results_put_the_earlier_one_first(self) -> None:
        """同じ時刻の行動の結果は、先に足したものを先に返す。並びを持っていたころと同じ順。"""
        store = UnifiedRecentEventStore()
        store.append_action_result(_PLAYER, _action(1, "先"))
        store.append_action_result(_PLAYER, _action(1, "後"))

        assert [e.action_summary for e in store.get_recent_action_results(_PLAYER, 2)] == ["先", "後"]

    def test_only_the_last_kept_count_of_results_are_kept(self) -> None:
        """RECENT_ACTION_RESULTS_KEPT 件を超えて足すと、古く足したものから捨てる。"""
        store = UnifiedRecentEventStore()
        for minute in range(RECENT_ACTION_RESULTS_KEPT + 3):
            store.append_action_result(_PLAYER, _action(minute, f"行動 {minute}"))

        kept = store.action_results_in_storage_order(_PLAYER)
        assert [e.action_summary for e in kept] == [
            f"行動 {minute}" for minute in range(3, RECENT_ACTION_RESULTS_KEPT + 3)
        ]

    def test_negative_limit_is_rejected(self) -> None:
        """limit に負の数を渡すと ValueError を投げる。"""
        with pytest.raises(ValueError):
            UnifiedRecentEventStore().get_recent_action_results(_PLAYER, -1)

    def test_replaced_results_are_kept_up_to_the_count(self) -> None:
        """snapshot から戻すときも、RECENT_ACTION_RESULTS_KEPT 件を超えた古いものは捨てる。"""
        store = UnifiedRecentEventStore()

        store.replace_action_results(
            _PLAYER, [_action(minute, f"行動 {minute}") for minute in range(RECENT_ACTION_RESULTS_KEPT + 1)]
        )

        assert len(store.action_results_in_storage_order(_PLAYER)) == RECENT_ACTION_RESULTS_KEPT


class TestObservationsAreNotKept:
    """観測は持たず、聞き手に知らせるだけであることを保証する。"""

    def test_appended_observation_is_not_kept(self) -> None:
        """観測を足しても、預かりにも行動の結果にも残らない。"""
        store = UnifiedRecentEventStore()

        store.append_observation(_PLAYER, _observation(1, "扉が開いた"))

        assert store.get_pending_observations(_PLAYER) == []
        assert store.action_results_in_storage_order(_PLAYER) == []


class TestPendingObservations:
    """手番の前に届いた観測を、取り出すまで預かることを保証する。"""

    def test_drain_returns_pending_observations_in_order_and_empties_them(self) -> None:
        """預かった観測は、取り出すと届いた順に返り、預かりは空になる。"""
        store = UnifiedRecentEventStore()
        store.append_pending_observation(_PLAYER, _observation(1, "扉が開いた"))
        store.append_pending_observation(_PLAYER, _observation(2, "鐘が鳴った"))

        drained = store.drain_pending_observations(_PLAYER)

        assert [e.output.prose for e in drained] == ["扉が開いた", "鐘が鳴った"]
        assert store.get_pending_observations(_PLAYER) == []

    def test_player_ids_include_players_with_pending_or_results(self) -> None:
        """預かりか行動の結果のあるプレイヤーを返す。"""
        store = UnifiedRecentEventStore()
        store.append_pending_observation(PlayerId(1), _observation(1, "扉が開いた"))
        store.append_action_result(PlayerId(2), _action(1, "扉を通った"))

        assert store.player_ids() == {1, 2}


class TestAppendListeners:
    """足した出来事を知らせる処理 (add_append_listener) が、足した順に聞き手へ渡すことを保証する。写す処理 (PlayerShortTermMemoryCopy) がこれで Being の短期記憶に書く (design_decisions D1824-7)。"""

    def test_listener_receives_observations_and_action_results_in_order(self) -> None:
        """観測と行動の結果を足すと、聞き手に 1 件ずつがその順で届く。"""
        store = UnifiedRecentEventStore()
        received: list[tuple[PlayerId, str]] = []
        store.add_append_listener(lambda pid, entry: received.append((pid, entry.kind)))

        store.append_observation(_PLAYER, _observation(1, "扉が開いた"))
        store.append_action_result(_PLAYER, _action(2, "扉を通った"))

        assert received == [(_PLAYER, "observation"), (_PLAYER, "action_result")]

    def test_pending_and_replaced_entries_are_not_announced(self) -> None:
        """未処理の観測の預かりと、snapshot から戻す置き換えは、足した出来事ではないので知らせない。"""
        store = UnifiedRecentEventStore()
        received: list[object] = []
        store.add_append_listener(lambda pid, entry: received.append(entry))

        store.append_pending_observation(_PLAYER, _observation(1, "扉が開いた"))
        store.replace_action_results(_PLAYER, [_action(2, "扉を通った")])

        assert received == []

    def test_removed_listener_is_no_longer_called(self) -> None:
        """外した聞き手には、そのあとに足した出来事を知らせない。"""
        store = UnifiedRecentEventStore()
        received: list[object] = []
        listener = lambda pid, entry: received.append(entry)  # noqa: E731
        store.add_append_listener(listener)

        store.remove_append_listener(listener)
        store.append_observation(_PLAYER, _observation(1, "扉が開いた"))

        assert received == []

    def test_non_callable_listener_is_rejected(self) -> None:
        """呼べない値を聞き手に渡すと TypeError を投げる。"""
        with pytest.raises(TypeError):
            UnifiedRecentEventStore().add_append_listener("not callable")  # type: ignore[arg-type]

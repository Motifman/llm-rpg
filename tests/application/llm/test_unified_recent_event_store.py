"""観測と行動を統一しても、従来の種類別 view と描画を保つことを保証する。"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
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


def test_unified_store_returns_both_kinds_in_occurred_at_order() -> None:
    """記録順が前後しても統一時系列は occurred_at の古い順になる。"""
    store = UnifiedRecentEventStore()
    store.append_action_result(_PLAYER, _action(3, "三番目の行動"))
    store.append_observation(_PLAYER, _observation(1, "最初の観測"))
    store.append_action_result(_PLAYER, _action(2, "二番目の行動"))

    timeline = store.get_timeline(_PLAYER)

    assert [entry.kind for entry in timeline] == [
        "observation",
        "action_result",
        "action_result",
    ]
    assert [entry.occurred_at for entry in timeline] == sorted(
        entry.occurred_at for entry in timeline
    )


def test_kind_views_return_only_the_requested_existing_dto_type() -> None:
    """種類別 view は他方を混ぜず、従来 DTO を新しい順で返す。"""
    store = UnifiedRecentEventStore()
    observations = [_observation(1, "観測1"), _observation(3, "観測2")]
    actions = [_action(2, "行動1"), _action(4, "行動2")]
    for entry in observations:
        store.append_observation(_PLAYER, entry)
    for entry in actions:
        store.append_action_result(_PLAYER, entry)

    assert store.get_recent_observations(_PLAYER, 20) == list(
        reversed(observations)
    )
    assert store.get_recent_action_results(_PLAYER, 20) == list(reversed(actions))


def test_recent_events_rendering_is_byte_identical_to_the_legacy_two_list_path() -> None:
    """旧2リスト経路と統一ストアの種類別 view は同じ本文を1バイトも変えない。"""
    observations = [_observation(1, "物音を聞いた。"), _observation(4, "扉が閉じた。")]
    actions = [_action(2, "周囲を見渡した"), _action(3, "声をかけた")]
    formatter = DefaultRecentEventsFormatter()
    legacy_text = formatter.format(
        list(reversed(observations)), list(reversed(actions))
    )

    store = UnifiedRecentEventStore()
    for entry in observations:
        store.append_observation(_PLAYER, entry)
    for entry in actions:
        store.append_action_result(_PLAYER, entry)
    unified_text = formatter.format_unified_entries(
        store.get_recent_timeline(
            _PLAYER,
            observation_limit=20,
            action_result_limit=20,
            newest_equal_observation_first=False,
        )
    )

    assert unified_text == legacy_text

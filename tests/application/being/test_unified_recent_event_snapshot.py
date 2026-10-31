"""直近の出来事のストアの snapshot が、v2 で未処理の観測と行動の結果を往復し、v1 と旧 3 形式も読めることを保証する (design_decisions D1824-24)。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    UnifiedRecentEventStoreSubsystemCodec,
    migrate_legacy_recent_event_subsystems,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PLAYER = PlayerId(1)
_NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
_OBSERVATION_PAYLOAD = {
    "occurred_at": _NOW.isoformat(),
    "game_time_label": "深夜 0:00",
    "output": {
        "prose": "旧観測",
        "structured": {},
        "observation_category": "self_only",
        "schedules_turn": False,
        "breaks_movement": False,
    },
}
_ACTION_PAYLOAD = {
    "occurred_at": _NOW.isoformat(),
    "action_summary": "旧行動",
    "result_summary": "旧結果",
    "success": True,
}


def _observation(prose: str) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_NOW,
        game_time_label="深夜 0:00",
        output=ObservationOutput(prose=prose, structured={}),
    )


def _runtime() -> SimpleNamespace:
    store = UnifiedRecentEventStore()
    return SimpleNamespace(
        _recent_event_store=store,
        _obs_buffer=DefaultObservationContextBuffer(event_store=store),
        _action_result_store=DefaultActionResultStore(event_store=store),
    )


def test_round_trip_keeps_action_results_and_pending_observations() -> None:
    """v2 で保存して戻すと、直近の行動の結果と未処理の観測が残る。足した観測は持たないので保存しない。"""
    source = _runtime()
    source._recent_event_store.append_observation(_PLAYER, _observation("足した観測"))
    source._obs_buffer.append(_PLAYER, _observation("未処理"))
    source._action_result_store.append(
        _PLAYER, "扉を調べた", "鍵が掛かっていた", occurred_at=_NOW, game_time_label="深夜 0:00"
    )
    codec = UnifiedRecentEventStoreSubsystemCodec()

    payload = codec.capture(source)
    destination = _runtime()
    codec.restore(destination, payload)

    assert set(payload) == {"schema_version", "action_results", "pending_observations"}
    assert payload["schema_version"] == 2
    assert [e.action_summary for e in destination._action_result_store.get_recent(_PLAYER, 20)] == ["扉を調べた"]
    assert [e.output.prose for e in destination._obs_buffer.get_observations(_PLAYER)] == ["未処理"]


def test_restore_clears_what_was_there_before() -> None:
    """戻す前にあった行動の結果と未処理の観測は消える。"""
    destination = _runtime()
    destination._obs_buffer.append(_PLAYER, _observation("前からあった"))
    destination._action_result_store.append(_PLAYER, "前の行動", "前の結果", occurred_at=_NOW)

    UnifiedRecentEventStoreSubsystemCodec().restore(
        destination, {"schema_version": 2, "action_results": [], "pending_observations": []}
    )

    assert destination._obs_buffer.get_observations(_PLAYER) == []
    assert destination._action_result_store.get_recent(_PLAYER, 20) == []


def test_v1_with_timeline_restores_action_results_and_drops_observations_and_summaries() -> None:
    """並びと要約を持つ v1 は、並びの中の行動の結果と未処理の観測だけを戻し、並びの観測と要約は捨てる。次の保存は v2 になる。"""
    v1 = {
        "schema_version": 1,
        "mode": "rolling_summary",
        "entries": [
            {
                "player_id": 1,
                "entries": [
                    {"occurred_at": _NOW.isoformat(), "kind": "observation", "payload": _OBSERVATION_PAYLOAD},
                    {"occurred_at": _NOW.isoformat(), "kind": "action_result", "payload": _ACTION_PAYLOAD},
                ],
            }
        ],
        "completed_turn_sizes": [{"player_id": 1, "sizes": [2]}],
        "pending_observations": [{"player_id": 1, "entries": [_OBSERVATION_PAYLOAD]}],
        "mid_summaries": [{"player_id": 1, "summaries": [{"summary_id": "l4"}]}],
    }
    runtime = _runtime()
    codec = UnifiedRecentEventStoreSubsystemCodec()

    codec.restore(runtime, v1)

    assert [e.action_summary for e in runtime._action_result_store.get_recent(_PLAYER, 20)] == ["旧行動"]
    assert [e.output.prose for e in runtime._obs_buffer.get_observations(_PLAYER)] == ["旧観測"]
    assert codec.capture(runtime)["schema_version"] == 2


@pytest.mark.parametrize("version", [0, 3, None])
def test_unknown_version_is_rejected(version: object) -> None:
    """v1 と v2 以外の版は ValueError で止める。"""
    with pytest.raises(ValueError, match="schema_version"):
        UnifiedRecentEventStoreSubsystemCodec().restore(_runtime(), {"schema_version": version})


@pytest.mark.parametrize(
    "sliding_header",
    [
        {"schema_version": 1},
        {"schema_version": 2, "mode": "sliding_window"},
        {"schema_version": 2, "mode": "rolling_summary", "long_summaries": [], "long_gen_indices": []},
    ],
    ids=["v1_without_mode", "v2_sliding_window", "v2_rolling_summary_with_long_summaries"],
)
def test_legacy_three_subsystems_migrate_and_resave_as_v2(sliding_header: dict[str, object]) -> None:
    """旧 3 subsystem (sliding_window / observation_buffer / action_result_store) は v1 の形に移してから読み、行動の結果と未処理の観測が戻る。次の保存は v2 の 1 形式だけになる。"""
    entries_key = "raw_entries" if sliding_header.get("mode") == "rolling_summary" else "entries"
    old = {
        "sliding_window": {
            **sliding_header,
            entries_key: [{"player_id": 1, "entries": [_OBSERVATION_PAYLOAD]}],
        },
        "observation_buffer": {"schema_version": 1, "entries": [{"player_id": 1, "entries": [_OBSERVATION_PAYLOAD]}]},
        "action_result_store": {"schema_version": 5, "entries": [{"player_id": 1, "entries": [_ACTION_PAYLOAD]}]},
    }

    migrated = migrate_legacy_recent_event_subsystems(old)
    runtime = _runtime()
    codec = UnifiedRecentEventStoreSubsystemCodec()
    codec.restore(runtime, migrated["recent_event_store"])

    assert set(migrated) == {"recent_event_store"}
    assert runtime._action_result_store.get_recent(_PLAYER, 20)[0].action_summary == "旧行動"
    assert runtime._obs_buffer.get_observations(_PLAYER)[0].output.prose == "旧観測"
    assert codec.capture(runtime)["schema_version"] == 2

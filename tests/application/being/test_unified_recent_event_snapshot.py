"""統一 recent-event subsystem と旧3形式からの移行を保証する。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    UnifiedRecentEventStoreSubsystemCodec,
    migrate_legacy_recent_event_subsystems,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
    SummarizingShortTermMemory,
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
        _short_term_memory=SummarizingShortTermMemory(event_store=store),
        _obs_buffer=DefaultObservationContextBuffer(event_store=store),
        _action_result_store=DefaultActionResultStore(event_store=store),
    )


def test_unified_snapshot_round_trip_preserves_both_kinds_and_pending() -> None:
    """新1形式の保存・復元で観測、行動、未処理観測を同時に保つ。"""
    source = _runtime()
    source._short_term_memory.append(_PLAYER, _observation("記憶済み"))
    source._obs_buffer.append(_PLAYER, _observation("未処理"))
    source._action_result_store.append(
        _PLAYER,
        "扉を調べた",
        "鍵が掛かっていた",
        occurred_at=_NOW,
        game_time_label="深夜 0:00",
    )
    source._short_term_memory.complete_turn(_PLAYER)
    source._short_term_memory.append(_PLAYER, _observation("次の未完了ターン"))
    codec = UnifiedRecentEventStoreSubsystemCodec()

    payload = codec.capture(source)
    destination = _runtime()
    codec.restore(destination, payload)

    assert [entry.output.prose for entry in destination._short_term_memory.get_recent(_PLAYER, 20)] == [
        "次の未完了ターン",
        "記憶済み",
    ]
    assert [entry.action_summary for entry in destination._action_result_store.get_recent(_PLAYER, 20)] == [
        "扉を調べた"
    ]
    assert [entry.output.prose for entry in destination._obs_buffer.get_observations(_PLAYER)] == ["未処理"]
    assert destination._recent_event_store.completed_turn_sizes(_PLAYER) == (2,)


@pytest.mark.parametrize(
    "sliding_header",
    [
        {"schema_version": 1},
        {"schema_version": 2, "mode": "sliding_window"},
    ],
    ids=["v1_without_mode", "v2_sliding_window"],
)
def test_legacy_three_subsystems_migrate_and_resave_as_one(
    sliding_header: dict[str, object],
) -> None:
    """固定容量の短期記憶で保存した旧3 subsystem (v1 と v2 の sliding_window) を要約する短期記憶へ読むと同じ内容になり、次の保存は rolling_summary の新1形式だけになる。"""
    observation_payload = {
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
    action_payload = {
        "occurred_at": _NOW.isoformat(),
        "action_summary": "旧行動",
        "result_summary": "旧結果",
        "success": True,
    }
    old = {
        "sliding_window": {
            **sliding_header,
            "entries": [{"player_id": 1, "entries": [observation_payload]}],
        },
        "observation_buffer": {
            "schema_version": 1,
            "entries": [{"player_id": 1, "entries": [observation_payload]}],
        },
        "action_result_store": {
            "schema_version": 5,
            "entries": [{"player_id": 1, "entries": [action_payload]}],
        },
    }

    migrated = migrate_legacy_recent_event_subsystems(old)
    runtime = _runtime()
    codec = UnifiedRecentEventStoreSubsystemCodec()
    codec.restore(runtime, migrated["recent_event_store"])
    resaved = {codec.subsystem_key: codec.capture(runtime)}

    assert set(resaved) == {"recent_event_store"}
    assert resaved["recent_event_store"]["mode"] == "rolling_summary"
    assert runtime._short_term_memory.get_recent(_PLAYER, 20)[0].output.prose == "旧観測"
    assert runtime._action_result_store.get_recent(_PLAYER, 20)[0].action_summary == "旧行動"
    assert runtime._obs_buffer.get_observations(_PLAYER)[0].output.prose == "旧観測"


def test_legacy_rolling_summary_with_long_summaries_migrates_without_them() -> None:
    """要約の要約 (L5) を持つ旧 rolling_summary の 3 subsystem を移し替えると、L5 は引き継がれず、読み込みも落ちない (#1824)。"""
    old_l5 = {
        "summary_id": "l5-old",
        "player_id": 1,
        "generation_index": 1,
        "generated_at": _NOW.isoformat(),
        "self_image": "探索者",
        "world_view": "危うい島",
        "is_fallback": False,
    }
    old = {
        "sliding_window": {
            "schema_version": 2,
            "mode": "rolling_summary",
            "raw_entries": [],
            "mid_summaries": [],
            "long_summaries": [{"player_id": 1, "summary": old_l5}],
            "long_gen_indices": [{"player_id": 1, "index": 1}],
        },
        "observation_buffer": {"schema_version": 1, "entries": []},
        "action_result_store": {"schema_version": 5, "entries": []},
    }

    migrated = migrate_legacy_recent_event_subsystems(old)
    runtime = _runtime()
    UnifiedRecentEventStoreSubsystemCodec().restore(runtime, migrated["recent_event_store"])

    assert "long_summaries" not in migrated["recent_event_store"]
    assert "long_gen_indices" not in migrated["recent_event_store"]
    assert not hasattr(runtime._short_term_memory, "_long")

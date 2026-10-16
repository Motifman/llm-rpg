"""回をやり直す読み込みで、前の回の世界の tick を記憶から外す挙動 (#1514)。"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.being import _memory_payload_codecs
from ai_rpg_world.application.being.world_clock_restart import (
    WORLD_TICK_FIELDS_BY_CODEC,
    WorldClockRestartCoverageError,
    restart_world_clock_in_payload,
)


def _payload(**overrides: object) -> str:
    base: dict[str, object] = {
        "schema_version": 1,
        "memo": [],
        "pending_predictions": [],
        "memory_turn": [7],
    }
    base.update(overrides)
    return json.dumps(base)


class TestRestartWorldClockInPayload:
    """前の回の世界の tick を持つ欄を、新しい回の始まりに置き換える挙動を保証する。"""

    def test_memo_ticks_become_round_start(self) -> None:
        """memo の追加と達成の tick は 0 になり、本文と実時刻はそのまま残る。"""
        memo = {
            "id": "m1",
            "content": "井戸は北",
            "added_at": "2026-10-10T00:00:00+00:00",
            "added_at_tick": 90,
            "fulfillment_context": {"completed_at": "2026-10-10T00:01:00+00:00", "completed_at_tick": 95},
        }

        out_json, report = restart_world_clock_in_payload(_payload(memo=[memo]))

        out = json.loads(out_json)["memo"][0]
        assert out["added_at_tick"] == 0
        assert out["fulfillment_context"]["completed_at_tick"] == 0
        assert out["content"] == "井戸は北"
        assert out["added_at"] == "2026-10-10T00:00:00+00:00"
        assert report.reset_tick_fields == 2

    def test_memo_without_tick_keeps_none(self) -> None:
        """tick を持たない memo は None のまま残り、書き換えの件数に数えない。"""
        memo = {"id": "m1", "content": "x", "added_at_tick": None, "fulfillment_context": None}

        out_json, report = restart_world_clock_in_payload(_payload(memo=[memo]))

        assert json.loads(out_json)["memo"][0]["added_at_tick"] is None
        assert report.reset_tick_fields == 0

    @pytest.mark.parametrize(
        ("key", "element"),
        [
            ("afterglow_entries", {"episode_id": "e3", "entered_tick": 85}),
            ("recall_slot_entries", {"episode_id": "e1", "entered_tick": 80}),
            ("recall_slot_cooldown", {"episode_id": "e2", "tick": 120}),
            ("recall_habituation_last_recalled", {"episode_id": "e4", "tick": 88}),
            ("belief_evidence_buffer", {"evidence_id": "b1", "tick": 70, "observed_turn": 12}),
            ("belief_evidence_received_event_ids", "exp-1@3"),
        ],
    )
    def test_removed_part_entries_of_old_snapshots_are_dropped(
        self, key: str, element: object
    ) -> None:
        """想起の階層と証拠のバッファを消す前 (#1631) の snapshot に残る欄は、前の回の tick を持っていても止めずに捨てる。"""
        payload = _payload(**{key: [element]})

        out_json, report = restart_world_clock_in_payload(payload)

        assert key not in json.loads(out_json)
        assert report.reset_tick_fields == 0

    def test_pending_predictions_of_old_snapshots_are_dropped_and_counted(self) -> None:
        """約束を消す前 (#1631) の snapshot に残る保留中の予測は、前の回の tick を持つので捨て、捨てた件数を報告する。"""
        pending = {"pending_id": "p1", "tick_from": 20, "tick_to": 25, "created_tick": 15}

        out_json, report = restart_world_clock_in_payload(_payload(pending_predictions=[pending, dict(pending, pending_id="p2")]))

        assert json.loads(out_json)["pending_predictions"] == []
        assert report.dropped_pending_predictions == 2

    def test_memory_turn_is_kept(self) -> None:
        """Being のターン数は回をまたいで続くので書き換えない。"""
        out_json, _ = restart_world_clock_in_payload(_payload())

        assert json.loads(out_json)["memory_turn"] == [7]

    def test_unknown_tick_field_left_nonzero_raises(self) -> None:
        """表に無い欄に 0 でない tick が残れば、書き戻す前に止める。"""
        payload = _payload(acquaintances=[{"name": "カイト", "last_met_tick": 30}])

        with pytest.raises(WorldClockRestartCoverageError, match="last_met_tick"):
            restart_world_clock_in_payload(payload)

    @pytest.mark.parametrize("value", [30.0, "30"])
    def test_unknown_tick_field_as_float_or_string_raises(self, value: object) -> None:
        """表に無い欄の tick が小数や文字列で書かれていても、書き戻す前に止める。"""
        payload = _payload(acquaintances=[{"name": "カイト", "last_met_tick": value}])

        with pytest.raises(WorldClockRestartCoverageError, match="last_met_tick"):
            restart_world_clock_in_payload(payload)

    def test_payload_without_listed_stores_passes_through(self) -> None:
        """表の store を持たない古い snapshot は、書き換え 0 件でそのまま通る。"""
        out_json, report = restart_world_clock_in_payload(json.dumps({"schema_version": 1, "memory_turn": [3]}))

        assert json.loads(out_json) == {"schema_version": 1, "memory_turn": [3]}
        assert report.reset_tick_fields == 0
        assert report.dropped_pending_predictions == 0


def _tick_keys_written_by_codecs() -> dict[str, frozenset[str]]:
    tree = ast.parse(Path(_memory_payload_codecs.__file__).read_text(encoding="utf-8"))
    found: dict[str, frozenset[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.endswith("_to_dict"):
            continue
        keys = {
            key.value
            for dict_node in ast.walk(node)
            if isinstance(dict_node, ast.Dict)
            for key in dict_node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and "tick" in key.value
        }
        if keys:
            found[node.name] = frozenset(keys)
    return found


class TestWorldTickFieldsTable:
    """snapshot の codec が書く tick の欄が、書き換えの表から漏れていないことを保証する。"""

    def test_every_tick_key_written_by_codecs_is_in_the_table(self) -> None:
        """codec が書く名前に tick を含む欄は、すべて表に載っている。"""
        assert _tick_keys_written_by_codecs() == WORLD_TICK_FIELDS_BY_CODEC


class TestRestartedPayloadRestoresIntoStores:
    """本物の codec が書いた snapshot を書き換えても、store に書き戻せることを保証する。"""

    def test_round_trip_through_real_codecs_starts_every_tick_at_zero(self) -> None:
        """前の回の tick を持つ記録を capture して書き換えると、復元後はどれも tick 0 になり、Being のターン数で持つ知り合いの記録はそのまま戻る。"""
        from datetime import datetime, timezone

        from tests.application.being.test_being_memory_snapshot_coverage import _make_service

        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        being = BeingId("ada")
        src = _make_service()
        src._memo.add_by_being(being, "井戸は北", current_tick=90)
        src._acquaintance.record_meeting(being, environment_name="島", name="カイト", turn=12)
        src._acquaintance.record_meeting(being, environment_name="島", name="カイト", turn=30)

        restarted, report = restart_world_clock_in_payload(src.capture(being))
        dst = _make_service()
        dst.restore(being, restarted)

        assert [m.added_at_tick for m in dst._memo.list_all_by_being(being)] == [0]
        assert dst._acquaintance.list_by_being(being) == src._acquaintance.list_by_being(being)
        assert report.reset_tick_fields == 1
        assert report.dropped_pending_predictions == 0

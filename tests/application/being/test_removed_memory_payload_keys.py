"""Being の snapshot の memory payload から、消した部品の欄を捨てる挙動 (#1631)。"""
from __future__ import annotations

import json

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.removed_memory_payload_keys import (
    REMOVED_MEMORY_PAYLOAD_KEYS,
    drop_removed_memory_payload_keys,
)


class TestDropRemovedMemoryPayloadKeys:
    """表のキーを payload から取り除き、取り除いたキーごとの件数を返す挙動を保証する。"""

    def test_listed_keys_are_dropped_and_counted_by_elements(self) -> None:
        """表のキーは取り除かれ、値が list なら要素数を件数にする。空の欄は取り除くが件数に載せない。ほかのキーは残る。"""
        payload = json.dumps({
            "schema_version": 1,
            "memo": [{"id": "m1"}, {"id": "m2"}],
            "pending_predictions": [],
            "acquaintances": [{"name": "カイト"}],
        })

        out_json, counts = drop_removed_memory_payload_keys(payload)

        assert json.loads(out_json) == {"schema_version": 1, "acquaintances": [{"name": "カイト"}]}
        assert counts == {"memo": 2}

    def test_non_list_value_counts_as_one(self) -> None:
        """値が list でない表のキーは 1 件と数える。"""
        _, counts = drop_removed_memory_payload_keys(json.dumps({"memo": {"id": "m1"}}))

        assert counts == {"memo": 1}

    def test_payload_without_listed_keys_passes_through(self) -> None:
        """表のキーを持たない payload は、そのままの文字列で返り、件数は空。"""
        payload = json.dumps({"schema_version": 1, "being_memo_book": []})

        out_json, counts = drop_removed_memory_payload_keys(payload)

        assert out_json == payload
        assert counts == {}

    def test_broken_json_is_left_for_restore_to_reject(self) -> None:
        """JSON として読めない payload は手を付けずに返し、restore の形式の検査に任せる。"""
        out_json, counts = drop_removed_memory_payload_keys("not json")

        assert out_json == "not json"
        assert counts == {}


class TestRemovedKeysTable:
    """消したキーの表が、いま snapshot が読み書きするキーと重ならないことを保証する。"""

    def test_no_removed_key_is_still_expected_by_the_snapshot_service(self) -> None:
        """表に載せたキーを snapshot の必須キーに残すと、表が捨てたあとで restore が欠けとして拒むので、重ならない。"""
        assert set(REMOVED_MEMORY_PAYLOAD_KEYS) & BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS == set()

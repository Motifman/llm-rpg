"""シナリオの ``initial_items`` が、起動時に実際にプレイヤーへ渡ることを保証する。

``grant_initial_items_to_inventory`` は存在し、loader も ``initial_items`` を
``player_spawns`` へパースしていたが、**本番経路から一度も呼ばれていなかった**。
つまり宣言は読まれるだけで誰にも配られず、実 run では全員が手ぶらで始まって
いた。「spec は組んだが誰も消費していない」静かな失敗である。

テストが通り続けていたのは、各テストが自分で
``grant_initial_items_to_inventory`` を呼んでフィクスチャを作っていたため。
テストが自前で配線してしまうと、本番の配線漏れを検出できない。だから本テストは
**``create_world_runtime`` の結果だけ**を見る。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V4 = _REPO_ROOT / "data" / "scenarios" / "survival_island_v4_coop.json"


def _owned_names(rt, player_id) -> set[str]:
    inv = rt._player_inventory_repo.find_by_id(player_id)
    assert inv is not None
    return {
        rt._item_spec_repo.find_by_id(s).name
        for s in collect_owned_item_spec_ids_from_inventory(inv, rt._item_repo)
    }


class TestInitialItemsReachThePlayer:
    """``create_world_runtime`` を呼んだだけで初期所持品が入っている。"""

    def test_each_player_starts_with_their_declared_items(self) -> None:
        """v4 の 4 人が、シナリオに宣言されたとおりの品を持って始まる。"""
        rt = create_world_runtime(_V4)
        by_name = {
            spawn.name: _owned_names(rt, pid)
            for spawn, pid in zip(rt.scenario.player_spawns, rt.get_player_ids())
        }
        assert by_name["エイダ"] == {"薬瓶の写真"}
        assert by_name["ノア"] == {"古い徽章"}
        assert by_name["リオ"] == {"結婚式の招待状", "火打ち石"}
        assert by_name["カイ"] == {"蔓のロープ"}

    def test_nobody_starts_empty_handed_when_items_are_declared(self) -> None:
        """宣言がある以上、空のインベントリで始まる player はいない。"""
        rt = create_world_runtime(_V4)
        for spawn, pid in zip(rt.scenario.player_spawns, rt.get_player_ids()):
            if spawn.initial_items:
                assert _owned_names(rt, pid), (
                    f"{spawn.name} に initial_items が宣言されているのに手ぶら"
                )

    def test_item_count_matches_the_declaration(self) -> None:
        """宣言した個数だけ入る (多くも少なくもならない)。"""
        rt = create_world_runtime(_V4)
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        for spawn, pid in zip(rt.scenario.player_spawns, rt.get_player_ids()):
            inv = rt._player_inventory_repo.find_by_id(pid)
            filled = sum(
                1
                for i in range(inv.max_slots)
                if inv.get_item_instance_id_by_slot(SlotId(i)) is not None
            )
            assert filled == len(spawn.initial_items), (
                f"{spawn.name}: 宣言 {len(spawn.initial_items)} 個に対し "
                f"{filled} 個入っている"
            )


class TestResumeDoesNotDuplicate:
    """snapshot からの再開で初期品が二重にならない。"""

    def test_restored_inventory_replaces_the_granted_one(self, tmp_path) -> None:
        """復元後の所持品は snapshot の内容そのもので、初期品が足されない。

        起動時 grant は毎回走るので、復元が「置き換え」でなく「追記」だと
        再開のたびに初期品が増える。増えても誰も気づかない静かな失敗になる
        ので、置き換えであることを固定する。
        """
        from ai_rpg_world.application.being.world_subsystems.player_inventory_codec import (
            PlayerInventorySubsystemCodec,
        )

        rt = create_world_runtime(_V4)
        pid = rt.get_player_ids()[0]
        before = _owned_names(rt, pid)
        assert before, "前提: 初期品が入っていること"

        # 「手ぶらで保存された run」を再現する。
        codec = PlayerInventorySubsystemCodec()
        captured = codec.capture(rt)
        for entry in captured["entries"]:
            for slot in entry["inventory_slots"]:
                slot["item_instance_id"] = None
            for slot in entry["equipment_slots"]:
                slot["item_instance_id"] = None
            entry["reserved_item_ids"] = []

        fresh = create_world_runtime(_V4)
        codec.restore(fresh, captured)

        assert _owned_names(fresh, pid) == set(), (
            "復元が置き換えではなく追記になっている。再開のたびに初期品が増える"
        )

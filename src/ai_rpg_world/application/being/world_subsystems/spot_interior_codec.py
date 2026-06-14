"""Spot interior subsystem codec (Phase 9-3b)。

戦略 C「selective dynamic-only capture」: SpotInterior 全体ではなく、run 中に
変わりうる **動的 field のみ** を save / restore する。restore は scenario
loader が初期化した SpotInterior に上書き merge する形を取る。

保存対象 (= 動的部分):

| Subset | 内容 |
|---|---|
| ``ground_items`` | 床に落ちた item の全リスト (= 完全保存) |
| ``objects[*]`` | object_id をキーに ``state`` / ``is_visible`` / ``puzzle`` / ``detail_read_by`` |
| ``discoverable_items[*]`` | item_spec_id をキーに ``is_discovered`` |
| ``sub_locations[*]`` | sub_location_id をキーに ``is_hidden`` |

scenario static metadata (interactions / description / trap def / 等) は
本 codec 対象外。restore 時に scenario loader が再度生成した interior に
動的部分を **上書き** する semantics。

## scenario JSON が変わったとき

scenario JSON で object を追加 / 削除 / リネームすると、snapshot 内の
object_id と現 SpotInterior の object_id が不一致になる可能性がある。
本 codec は **「snapshot 側に存在するが scenario 側に存在しない」** の
ケースを info ログで skip する (= forward compat 風)。

「scenario 側にあるが snapshot 側にない object」は **scenario 初期値を
維持** する (= snapshot 取られた時にまだ存在しなかった新 object なので、
初期状態でよい)。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

logger = logging.getLogger(__name__)

SUBSYSTEM_KEY = "spot_interior"
SCHEMA_VERSION = 1


class SpotInteriorSubsystemCodec(WorldSubsystemCodec):
    """SpotInterior の動的部分のみ save / restore する codec。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_spot_interior_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._spot_interior_repo not found; "
                "SpotInteriorSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        # ``_data`` は ``InMemorySpotInteriorRepository`` の内部 dict。
        # ISpotInteriorRepository に enumerate API がないため private 経由。
        all_data = getattr(repo, "_data", {})
        # 決定的順序のため spot_id でソート。
        sorted_items = sorted(all_data.items(), key=lambda kv: int(kv[0].value))
        for spot_id, interior in sorted_items:
            ground = [
                {
                    "item_instance_id": int(gi.item_instance_id.value),
                    "item_spec_id": int(gi.item_spec_id.value),
                }
                for gi in interior.ground_items
            ]
            objects = []
            for obj in interior.objects:
                puzzle_data: dict[str, Any] | None = None
                if obj.puzzle is not None:
                    p = obj.puzzle
                    puzzle_data = {
                        "puzzle_type": str(p.puzzle_type),
                        "solution": list(p.solution),
                        "current_input": list(p.current_input),
                        "is_solved": bool(p.is_solved),
                        "max_attempts": p.max_attempts,
                        "attempts": int(p.attempts),
                    }
                objects.append(
                    {
                        "object_id": int(obj.object_id.value),
                        "state": dict(obj.state),
                        "is_visible": bool(obj.is_visible),
                        "puzzle": puzzle_data,
                        "detail_read_by": sorted(
                            int(p) for p in obj.detail_read_by
                        ),
                    }
                )
            discoverables = [
                {
                    "item_spec_id": int(d.item_spec_id.value),
                    "is_discovered": bool(d.is_discovered),
                }
                for d in interior.discoverable_items
            ]
            sub_locations = [
                {
                    "sub_location_id": int(sl.sub_location_id.value),
                    "is_hidden": bool(sl.is_hidden),
                }
                for sl in interior.sub_locations
            ]
            entries.append(
                {
                    "spot_id": int(spot_id.value),
                    "ground_items": ground,
                    "objects": objects,
                    "discoverable_items": discoverables,
                    "sub_locations": sub_locations,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": entries,
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        from ai_rpg_world.domain.item.value_object.item_instance_id import (
            ItemInstanceId,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.ground_item import (
            GroundItem,
        )
        from ai_rpg_world.domain.world_graph.value_object.puzzle_state import (
            PuzzleState,
        )

        repo = getattr(runtime, "_spot_interior_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._spot_interior_repo not found; "
                "SpotInteriorSubsystemCodec requires it"
            )

        for entry in data.get("entries", []):
            spot_id = SpotId(int(entry["spot_id"]))
            current_interior = repo.find_by_spot_id(spot_id)
            if current_interior is None:
                # scenario 側に当該 spot がない (= scenario JSON が変わった等)。
                # forward compat: info ログを残して skip。
                logger.info(
                    "spot_interior restore: spot_id=%s not in current scenario; "
                    "skipping (snapshot vs scenario mismatch — forward compat)",
                    spot_id.value,
                )
                continue

            # ground_items: 完全置換
            new_ground = tuple(
                GroundItem(
                    item_instance_id=ItemInstanceId(int(g["item_instance_id"])),
                    item_spec_id=ItemSpecId(int(g["item_spec_id"])),
                )
                for g in entry.get("ground_items", [])
            )

            # objects: object_id keyed lookup で動的 field のみ merge
            captured_objects_by_id = {
                int(o["object_id"]): o for o in entry.get("objects", [])
            }
            new_objects = []
            for cur_obj in current_interior.objects:
                cap = captured_objects_by_id.get(int(cur_obj.object_id.value))
                if cap is None:
                    # scenario に新たに増えた object: 初期状態のまま (snapshot
                    # 取った時にはなかった)。
                    new_objects.append(cur_obj)
                    continue
                # 動的 field を上書き
                new_puzzle = cur_obj.puzzle
                cap_puzzle = cap.get("puzzle")
                if cap_puzzle is not None:
                    new_puzzle = PuzzleState(
                        puzzle_type=str(cap_puzzle["puzzle_type"]),
                        solution=tuple(cap_puzzle.get("solution", ())),
                        current_input=tuple(cap_puzzle.get("current_input", ())),
                        is_solved=bool(cap_puzzle["is_solved"]),
                        max_attempts=cap_puzzle.get("max_attempts"),
                        attempts=int(cap_puzzle.get("attempts", 0)),
                    )
                elif cur_obj.puzzle is not None and cap.get("puzzle") is None:
                    # snapshot 時点では puzzle なしだったが scenario 側に
                    # ある: scenario 初期値を維持する (= 上書きしない)
                    new_puzzle = cur_obj.puzzle
                new_obj = replace(
                    cur_obj,
                    state=dict(cap.get("state", {})),
                    is_visible=bool(cap["is_visible"]),
                    puzzle=new_puzzle,
                    detail_read_by=frozenset(
                        int(p) for p in cap.get("detail_read_by", [])
                    ),
                )
                new_objects.append(new_obj)

            # discoverable_items: item_spec_id keyed で is_discovered 上書き
            captured_disc_by_spec = {
                int(d["item_spec_id"]): bool(d["is_discovered"])
                for d in entry.get("discoverable_items", [])
            }
            new_discoverables = []
            for cur_d in current_interior.discoverable_items:
                cap_v = captured_disc_by_spec.get(int(cur_d.item_spec_id.value))
                if cap_v is None:
                    new_discoverables.append(cur_d)
                else:
                    new_discoverables.append(replace(cur_d, is_discovered=cap_v))

            # sub_locations: sub_location_id keyed で is_hidden 上書き
            captured_sl_by_id = {
                int(s["sub_location_id"]): bool(s["is_hidden"])
                for s in entry.get("sub_locations", [])
            }
            new_sub_locations = []
            for cur_sl in current_interior.sub_locations:
                cap_v = captured_sl_by_id.get(int(cur_sl.sub_location_id.value))
                if cap_v is None:
                    new_sub_locations.append(cur_sl)
                else:
                    new_sub_locations.append(replace(cur_sl, is_hidden=cap_v))

            new_interior = replace(
                current_interior,
                sub_locations=tuple(new_sub_locations),
                objects=tuple(new_objects),
                ground_items=new_ground,
                discoverable_items=tuple(new_discoverables),
            )
            repo.save(spot_id, new_interior)


__all__ = [
    "SpotInteriorSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]

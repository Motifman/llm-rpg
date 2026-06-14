"""ItemInstance subsystem codec (Phase 9-3b)。

戦略 C: ``ItemInstance`` の **動的部分のみ** save / restore する。
``ItemAggregate`` の中の ``_item_instance`` を持つ。動的部分:

- ``quantity`` (= スタック数、消費 / 取得で変動)
- ``durability.current`` (= 現耐久。max は spec 由来で静的)
- ``state`` (= per-instance の任意 flat dict、JSON primitive 限定)

静的 metadata (= ``item_spec``, ``item_instance_id``, ``durability.max_value``)
は scenario / ItemSpec で決まるため capture せず、restore 時には現 aggregate
の値をそのまま使う。

scenario JSON が変わって ItemInstance が削除されている場合、snapshot 側に
あるが repo にない ID は info ログで skip (= forward compat)。

NOTE: ``ItemInstance`` は player の inventory に入っているもの、spot に
落ちているもの、両方を含む。本 codec は **repo 全体を走査** して全 instance
を 1 度に save する。inventory / spot 配置の関係は ``player_inventory`` /
``spot_interior`` codec が別途持つ。
"""

from __future__ import annotations

import logging
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

logger = logging.getLogger(__name__)

SUBSYSTEM_KEY = "item_instance"
SCHEMA_VERSION = 1


class ItemInstanceSubsystemCodec(WorldSubsystemCodec):
    """全 ItemInstance の quantity / durability / state を JSON 化。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        repo = getattr(runtime, "_item_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._item_repo not found; "
                "ItemInstanceSubsystemCodec requires it"
            )
        entries: list[dict[str, Any]] = []
        # ItemRepository が ``find_all`` を持つので enumerate 可能。
        for aggregate in repo.find_all():
            inst = aggregate.item_instance
            durability_current = (
                int(inst.durability.current)
                if inst.durability is not None
                else None
            )
            entries.append(
                {
                    "item_instance_id": int(inst.item_instance_id.value),
                    "quantity": int(inst.quantity),
                    "durability_current": durability_current,
                    "state": dict(inst.state),
                }
            )
        # item_instance_id でソート (= 決定的順序)。
        entries.sort(key=lambda d: d["item_instance_id"])
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
        from ai_rpg_world.domain.item.value_object.durability import Durability
        from ai_rpg_world.domain.item.value_object.item_instance_id import (
            ItemInstanceId,
        )

        repo = getattr(runtime, "_item_repo", None)
        if repo is None:
            raise RuntimeError(
                "runtime._item_repo not found; "
                "ItemInstanceSubsystemCodec requires it"
            )

        for entry in data.get("entries", []):
            iid = ItemInstanceId(int(entry["item_instance_id"]))
            aggregate = repo.find_by_id(iid)
            if aggregate is None:
                # scenario 側に該当 ItemInstance がない (= scenario が item を
                # 削除 / 変更した等)。forward compat で skip。
                logger.info(
                    "item_instance restore: item_instance_id=%s not found in "
                    "repo; skipping (snapshot vs scenario mismatch)",
                    iid.value,
                )
                continue
            inst = aggregate.item_instance

            # quantity: 直接 setter があれば使う。なければ set_quantity を試す。
            new_quantity = int(entry["quantity"])
            if hasattr(inst, "set_quantity"):
                try:
                    inst.set_quantity(new_quantity)
                except Exception as exc:
                    # set_quantity が invariant (max_stack_size 等) で raise
                    # する可能性。snapshot が無効 = scenario 変更を疑う。
                    logger.warning(
                        "set_quantity failed for item_instance_id=%s: %s; "
                        "skipping quantity restore for this item",
                        iid.value,
                        exc,
                    )

            # durability: 現値だけ復元。max は spec 由来で変えない。
            cap_dur = entry.get("durability_current")
            if cap_dur is not None and inst.durability is not None:
                # Durability(max_value, current) を新たに作って差し替え
                # (= private 直書き換え; 既存 setter がない場合の常套手段)。
                inst._durability = Durability(
                    max_value=int(inst.durability.max_value),
                    current=int(cap_dur),
                )

            # state: replace_state がある = それを使う (validation 走る)。
            new_state = dict(entry.get("state", {}))
            if hasattr(inst, "replace_state"):
                inst.replace_state(new_state)
            else:
                inst._state = new_state

            # 永続化 + event クリア (snapshot semantics)
            if hasattr(aggregate, "_events"):
                aggregate._events.clear()
            repo.save(aggregate)


__all__ = [
    "ItemInstanceSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]

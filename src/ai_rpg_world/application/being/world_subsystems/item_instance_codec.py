"""ItemInstance subsystem codec (Phase 9-3b)。

戦略 C: ``ItemInstance`` の **動的部分 + 再生成に必要な spec 参照** を
保存 / 復元する。``ItemAggregate`` の中の ``_item_instance`` を持つ。
保存対象:

- ``item_spec_id`` (= restore 先で動的生成 instance が未存在なら spec repo から
  再生成するための静的参照)
- ``quantity`` (= スタック数、消費 / 取得で変動)
- ``durability.current`` (= 現耐久。max は spec 由来で静的)
- ``state`` (= per-instance の任意 flat dict、JSON primitive 限定)

静的な情報本体 (= ``ItemSpec`` の name / description / effects 等) は
シナリオ / ``ItemSpec`` repository で決まるため保存せず、復元時には現
``ItemAggregate`` または ``_item_spec_repo`` の値を使う。

シナリオ JSON が変わって ``ItemInstance`` または ``ItemSpec`` が一致しない
場合は fail-fast する。inventory / spot_interior が同じ ID を参照している
状態で item 本体だけ欠けると、再開後に静かな失敗になるため。

NOTE: ``ItemInstance`` は player の inventory に入っているもの、spot に
落ちているもの、両方を含む。本 codec は **repo 全体を走査** して全 instance
を 1 度に保存する。inventory / spot 配置の関係は ``player_inventory`` /
``spot_interior`` codec が別途持つ。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)

SUBSYSTEM_KEY = "item_instance"
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})


def _advance_item_instance_id_sequence(repo: Any, max_seen_id: int) -> None:
    """snapshot で復元した ID より後から次の item instance を採番させる。

    復元で ``ItemInstanceId(12)`` を repo に作っても、採番器が 1 のままだと
    再開後の収穫・ドロップ報酬などが同じ ID を再発行し得る。snapshot restore
    専用に、既知の repository 実装の採番状態を「最大復元 ID 以上」まで進める。
    """
    if max_seen_id <= 0:
        return

    data_store = getattr(repo, "_data_store", None)
    if data_store is not None and hasattr(data_store, "next_item_instance_id"):
        current = int(data_store.next_item_instance_id)
        if current <= max_seen_id:
            data_store.next_item_instance_id = max_seen_id + 1
        return

    conn = getattr(repo, "_conn", None)
    if conn is not None:
        conn.execute(
            "INSERT OR IGNORE INTO game_sequences (name, next_value) VALUES (?, ?)",
            ("item_instance_id", max_seen_id),
        )
        conn.execute(
            "UPDATE game_sequences SET next_value = ? "
            "WHERE name = ? AND next_value < ?",
            (max_seen_id, "item_instance_id", max_seen_id),
        )
        if getattr(repo, "_commits_after_write", False):
            conn.commit()


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
                    "item_spec_id": int(inst.item_spec.item_spec_id.value),
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
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)})"
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

        max_seen_id = 0
        for entry in data.get("entries", []):
            iid = ItemInstanceId(int(entry["item_instance_id"]))
            max_seen_id = max(max_seen_id, iid.value)
            aggregate = repo.find_by_id(iid)
            new_quantity = int(entry["quantity"])
            spec_id_raw = entry.get("item_spec_id")
            if int(version) >= 2 and spec_id_raw is None:
                raise RuntimeError(
                    "item_instance restore: schema_version=2 entry is missing "
                    f"item_spec_id for item_instance_id={iid.value}"
                )
            if aggregate is None:
                # 実行中に生成された item instance は、新しい runtime の
                # _item_repo にはまだ存在しない。snapshot に保存された
                # item_spec_id をもとに scenario 側の ItemSpec から再生成する。
                # spec 自体が存在しない場合は、inventory / spot 側に孤児参照
                # が残るため fail-fast する。
                item_spec_repo = getattr(runtime, "_item_spec_repo", None)
                spec = None
                if item_spec_repo is not None and spec_id_raw is not None:
                    from ai_rpg_world.domain.item.value_object.item_spec_id import (
                        ItemSpecId,
                    )

                    spec_read_model = item_spec_repo.find_by_id(
                        ItemSpecId(int(spec_id_raw))
                    )
                    if spec_read_model is not None:
                        spec = (
                            spec_read_model.to_item_spec()
                            if hasattr(spec_read_model, "to_item_spec")
                            else spec_read_model
                        )
                if spec is None:
                    raise RuntimeError(
                        "item_instance restore: item_instance_id=%s not found in "
                        "repo and item_spec_id=%r cannot be resolved "
                        "(snapshot vs scenario mismatch)"
                        % (iid.value, spec_id_raw)
                    )
                from ai_rpg_world.domain.item.aggregate.item_aggregate import (
                    ItemAggregate,
                )

                cap_dur = entry.get("durability_current")
                durability = None
                if cap_dur is not None and spec.durability_max is not None:
                    from ai_rpg_world.domain.item.value_object.durability import (
                        Durability,
                    )

                    durability = Durability(
                        max_value=int(spec.durability_max),
                        current=int(cap_dur),
                    )
                elif cap_dur is not None:
                    raise RuntimeError(
                        "item_instance restore: item_instance_id="
                        f"{iid.value} has durability_current={cap_dur!r} but "
                        "current ItemSpec does not support durability"
                    )
                aggregate = ItemAggregate.create(
                    iid,
                    spec,
                    durability=durability,
                    quantity=new_quantity,
                    state=dict(entry.get("state", {})),
                )
                repo.save(aggregate)
                aggregate = repo.find_by_id(iid)
                if aggregate is None:
                    raise RuntimeError(
                        "item_instance restore: created item_instance_id="
                        f"{iid.value} but repo.find_by_id returned None"
                    )
            inst = aggregate.item_instance
            if spec_id_raw is not None:
                current_spec_id = int(inst.item_spec.item_spec_id.value)
                captured_spec_id = int(spec_id_raw)
                if current_spec_id != captured_spec_id:
                    raise RuntimeError(
                        "item_instance restore: item_instance_id="
                        f"{iid.value} spec mismatch "
                        f"(snapshot={captured_spec_id}, current={current_spec_id})"
                    )

            # quantity: 直接 setter があれば使う。なければ set_quantity を試す。
            if new_quantity == 0:
                # ItemInstance の constructor は quantity=0 を許容するが
                # set_quantity は通常操作用なので 0 を拒否する。snapshot restore
                # は保存済み状態の再現なので、0 も直接復元する。
                inst._quantity = 0
            elif hasattr(inst, "set_quantity"):
                try:
                    inst.set_quantity(new_quantity)
                except Exception as exc:
                    # set_quantity が invariant (max_stack_size 等) で raise
                    # する場合、snapshot と現シナリオの静的定義が食い違っている。
                    raise RuntimeError(
                        "set_quantity failed for item_instance_id=%s: %s; "
                        "snapshot does not match current ItemSpec"
                        % (iid.value, exc)
                    ) from exc

            # durability: 現値だけ復元。max は spec 由来で変えない。
            cap_dur = entry.get("durability_current")
            if cap_dur is not None and inst.durability is not None:
                # Durability(max_value, current) を新たに作って差し替え
                # (= private 直書き換え; 既存 setter がない場合の常套手段)。
                inst._durability = Durability(
                    max_value=int(inst.durability.max_value),
                    current=int(cap_dur),
                )
            elif cap_dur is not None:
                raise RuntimeError(
                    "item_instance restore: item_instance_id="
                    f"{iid.value} has durability_current={cap_dur!r} but "
                    "current ItemSpec does not support durability"
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
        _advance_item_instance_id_sequence(repo, max_seen_id)


__all__ = [
    "ItemInstanceSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]

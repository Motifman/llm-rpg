"""Encounter Memory subsystem codec (PR2)。

``runtime._encounter_memory`` (= ``InMemoryEncounterMemory``) は player ごとに
「自分が遭遇した対象 (entity / spot / event-type)」の familiarity 信号を保持する。
詳細は ``docs/memory_system/perception_memory_join_design.md`` を参照。

resume 時にこれが空だと:

- 「初対面 / 再会」の区別が agent から消える (= 半年ぶりに会う相手にも初対面の
  反応をしてしまう)
- 「初訪問 / 再訪」の区別も同様に消える

特に長期 run / 中断 → 再開 のユースケースでは、Encounter Memory の永続化が
agent の連続性そのものに直結する。

設計判断:

- 本 codec は ``InMemoryEncounterMemory`` に依存する (``_store`` 直接アクセス)。
  別実装が出てきたタイミングで codec 側を改修する方針で、silent fallback は
  持たない (= dead code の温床にしない)
- ``count`` と ``first_seen_tick`` を厳密に復元したいので、restore で
  ``observe()`` は呼ばない (それを呼ぶと count が 1 加算され、first_seen が
  上書きされる)。代わりに内部 store に直書きする
- 順序は決定的: player_id 昇順 / canonical key 昇順 (snapshot diff の noise を
  減らすため)
"""

from __future__ import annotations

from typing import Any, Dict

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_record import (
    EncounterRecord,
)


SUBSYSTEM_KEY = "encounter_memory"
SCHEMA_VERSION = 1


class EncounterMemorySubsystemCodec(WorldSubsystemCodec):
    """``_encounter_memory`` (= ``InMemoryEncounterMemory``) を JSON 化。

    保存フォーマット (schema_version=1):

    ```json
    {
      "schema_version": 1,
      "entries": [
        {
          "player_id": 1,
          "records": [
            {
              "key": "player:noa",
              "first_seen_tick": 5,
              "last_seen_tick": 42,
              "count": 3
            },
            ...
          ]
        },
        ...
      ]
    }
    ```
    """

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    # ────────────────────────────────────────────────────────
    # capture
    # ────────────────────────────────────────────────────────

    def capture(self, runtime: Any) -> dict[str, Any]:
        memory = self._require_in_memory(runtime)
        # InMemoryEncounterMemory._store: Dict[int, Dict[str, EncounterRecord]]
        # = {player_id_int → {canonical_key_string → record}}。
        # 直接 iterate して double round-trip (canonical → EncounterKey →
        # canonical) を回避する。
        store: Dict[int, Dict[str, EncounterRecord]] = memory._store
        entries = [
            {
                "player_id": int(pid_value),
                "records": [
                    {
                        "key": canonical,
                        "first_seen_tick": int(record.first_seen_tick),
                        "last_seen_tick": int(record.last_seen_tick),
                        "count": int(record.count),
                    }
                    for canonical, record in sorted(
                        records_by_canonical.items()
                    )
                ],
            }
            for pid_value, records_by_canonical in sorted(store.items())
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": entries,
        }

    # ────────────────────────────────────────────────────────
    # restore
    # ────────────────────────────────────────────────────────

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        memory = self._require_in_memory(runtime)
        # InMemoryEncounterMemory._store: Dict[int, Dict[str, EncounterRecord]]。
        # 全消ししてから書き戻す (= 部分復元による不整合を防ぐ)。
        store: Dict[int, Dict[str, EncounterRecord]] = memory._store
        store.clear()

        # entries 欠落は空として扱う (forward-compat: 上位 schema 変更への防衛)
        for entry in data.get("entries", []):
            pid_value = int(entry["player_id"])
            for record_dict in entry.get("records", []):
                # EncounterKey.from_canonical で kind:identifier 形式を検証 +
                # parse。不正形式なら EncounterKeyValidationException が surface
                key = EncounterKey.from_canonical(str(record_dict["key"]))
                # EncounterRecord を直接構築。__post_init__ で不変条件 (count>=1,
                # first<=last 等) を検証する。不正 payload なら
                # EncounterRecordValidationException が surface。
                record = EncounterRecord(
                    first_seen_tick=int(record_dict["first_seen_tick"]),
                    last_seen_tick=int(record_dict["last_seen_tick"]),
                    count=int(record_dict["count"]),
                )
                store.setdefault(pid_value, {})[key.canonical] = record

    @staticmethod
    def _require_in_memory(runtime: Any) -> InMemoryEncounterMemory:
        """``runtime._encounter_memory`` が ``InMemoryEncounterMemory`` であることを保証。

        本 codec は ``_store`` 直接アクセスを前提とする (= count / first_seen の
        厳密復元のため)。別実装が出たら codec 側を改修する方針なので、ここでは
        silent fallback ではなく fail-fast する。
        """
        memory = getattr(runtime, "_encounter_memory", None)
        if memory is None:
            raise RuntimeError(
                "runtime._encounter_memory not found; "
                "EncounterMemorySubsystemCodec requires it"
            )
        if not isinstance(memory, InMemoryEncounterMemory):
            raise NotImplementedError(
                f"EncounterMemorySubsystemCodec currently supports only "
                f"InMemoryEncounterMemory (got {type(memory).__name__}). "
                f"Add a codec variant when a new implementation lands."
            )
        return memory


__all__ = [
    "EncounterMemorySubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]

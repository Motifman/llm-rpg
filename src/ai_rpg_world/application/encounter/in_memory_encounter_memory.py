"""``IEncounterMemory`` の in-memory 実装。

player_id (int) → EncounterKey.canonical (str) → EncounterRecord の二重 dict を
保持する単純な実装。Phase 1 (PR1) のスコープでは:

- 単 thread 前提 (observation pipeline は main thread のみが触る)。並行アクセスが
  必要になった段階で lock を追加する。silent failure を避けるため、現状の前提を
  ここに明記しておく
- 永続化は別 PR (PR2 で snapshot codec を追加) で対応する。本 instance は
  メモリ上にのみ存在し、process 終了で失われる
- 「忘却」は入れない。観測されたら永遠に保持する
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from ai_rpg_world.application.encounter.contracts.interfaces import (
    IEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterRecordValidationException,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_record import (
    EncounterRecord,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryEncounterMemory(IEncounterMemory):
    """player_id → key canonical → EncounterRecord の in-memory 実装。"""

    def __init__(self) -> None:
        # player_id.value (int) → canonical key (str) → record
        self._store: Dict[int, Dict[str, EncounterRecord]] = {}

    # ────────────────────────────────────────────────────────
    # IEncounterMemory
    # ────────────────────────────────────────────────────────

    def observe(
        self,
        player_id: PlayerId,
        key: EncounterKey,
        current_tick: int,
    ) -> EncounterRecord:
        if not isinstance(player_id, PlayerId):
            raise TypeError(f"player_id must be PlayerId (got {type(player_id)!r})")
        if not isinstance(key, EncounterKey):
            raise TypeError(f"key must be EncounterKey (got {type(key)!r})")
        # current_tick の型 / 範囲チェックを EncounterRecord に委ねると、エラー
        # メッセージの field 名が "first_seen_tick" / "now_tick" になり、observation
        # pipeline 側からの debug が遠回りになる。ここで argument 名のまま fail-fast
        # する (CLAUDE.md "domain では ValidationException を使う" / 引数チェックは
        # application 層でも domain 例外を使って良い文脈)。
        if not isinstance(current_tick, int) or isinstance(current_tick, bool):
            raise EncounterRecordValidationException("current_tick must be int")
        if current_tick < 0:
            raise EncounterRecordValidationException(
                f"current_tick must be >= 0 (got {current_tick})"
            )

        pid = player_id.value
        bucket = self._store.setdefault(pid, {})
        canonical = key.canonical
        existing = bucket.get(canonical)
        if existing is None:
            record = EncounterRecord.first(now_tick=current_tick)
        else:
            record = existing.observed_again(now_tick=current_tick)
        bucket[canonical] = record
        return record

    def lookup(
        self,
        player_id: PlayerId,
        key: EncounterKey,
    ) -> Optional[EncounterRecord]:
        if not isinstance(player_id, PlayerId):
            raise TypeError(f"player_id must be PlayerId (got {type(player_id)!r})")
        if not isinstance(key, EncounterKey):
            raise TypeError(f"key must be EncounterKey (got {type(key)!r})")
        bucket = self._store.get(player_id.value)
        if bucket is None:
            return None
        return bucket.get(key.canonical)

    def get_records_for(
        self,
        player_id: PlayerId,
    ) -> Mapping[EncounterKey, EncounterRecord]:
        if not isinstance(player_id, PlayerId):
            raise TypeError(f"player_id must be PlayerId (got {type(player_id)!r})")
        bucket = self._store.get(player_id.value)
        if bucket is None:
            return {}
        # canonical str → record を、EncounterKey → record に変換して返す
        # (snapshot codec が EncounterKey で iterate しやすくする)
        return {
            EncounterKey.from_canonical(canonical): record
            for canonical, record in bucket.items()
        }


__all__ = ["InMemoryEncounterMemory"]

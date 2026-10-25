"""BeingMemorySnapshotService — Being 単位で memory store を JSON 1 本に save / restore する。

Phase 4 Step 4-2b (Issue #470): run 途中再開 (mid-run resume) を実現するため、
Phase 4-1 で導入した ``BeingSnapshot.memory_payload_json`` (オペーク JSON)
の **中身を作る・読む application service** を提供する。

新 store を足すときの手順は ``EXPECTED_PAYLOAD_KEYS``
近くの docstring を参照。

責務:

- ``capture(being_id) -> str``: 各 store の状態を読み出し、内部 schema v1 の
  JSON 文字列にシリアライズ
- ``restore(being_id, payload_json) -> None``: JSON 文字列を 各 store に
  bulk overwrite で書き戻す。**best-effort: store ごとに順番に書き戻す
  (cross-store atomicity なし)**。各 store 内では Phase 4-2a の
  ``replace_all_*_by_being`` が single-transaction を保証する

## JSON Schema (内部 v1)

```json
{
  "schema_version": 1,
  ...
}
```

各 list の要素 VO ↔ dict は ``_memory_payload_codecs`` モジュールが担当する。
``schema_version`` は本 service が版管理する内部 schema 番号で、
``BeingSnapshot.snapshot_version`` (= VO schema 番号) とは独立に進化させる。

## restore の atomicity

各 store の ``replace_all_*_by_being`` は単一 transaction (sqlite) または
原子的 dict 操作 (in-memory) で **store 内 atomicity を保証する**。一方
本 service は **複数 store に跨る atomicity は保証しない** (= 設計判断、
各 store は独立したリソースで 2-phase commit を導入するコストに見合わない)。
代わりに:

1. 全 store を順序を決めて書き換える (失敗順序が予測可能)
2. **読み出し → 復元前バックアップ → 書き込み** という pattern を取る
   オプションは 4-2c 以降の課題 (本 PR scope 外)
3. 失敗時は store ごとの例外を呼出側に伝播 (silent failure 禁止)

実運用では:

- 復元は **新規 / 初期化済 store** に対して行う想定 (= まだ書き込みがない)
- もし既存データに対して復元するなら、呼出側で「失敗時に元データに戻せる
  ように事前 capture しておく」運用が必要 (= Phase 5 で use case 層が
  責務を持つ)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.being._memory_payload_codecs import (
    acquaintance_to_dict,
    being_episode_to_dict,
    being_memo_to_dict,
    being_short_term_memory_to_dict,
    dict_to_acquaintance,
    dict_to_being_episode,
    dict_to_being_memo,
    dict_to_being_short_term_memory,
)
from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.memo_book import MemoBook, MemoBookRepository
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnClock
from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemory,
    ShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import MemoValidationException
from ai_rpg_world.domain.being.value_object.being_id import BeingId

CURRENT_PAYLOAD_SCHEMA_VERSION: int = 1
SUPPORTED_PAYLOAD_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


def _decode_list(
    raw_list: list[Any],
    decoder: Callable[[Any], Any],
    key: str,
) -> list[Any]:
    """list の各 dict 要素を ``decoder`` で VO に変換。エラーは format error に wrap。

    payload 形式エラー (= dict key 欠落、enum 未知値、型不一致) は
    ``KeyError`` / ``ValueError`` / ``TypeError`` で発生しうるが、呼出側に
    「形式の問題」として一律で見せるため ``BeingMemoryPayloadFormatError``
    に wrap する (= code-reviewer HIGH 指摘対応)。
    """
    out = []
    for idx, item in enumerate(raw_list):
        try:
            out.append(decoder(item))
        except (KeyError, ValueError, TypeError) as exc:
            raise BeingMemoryPayloadFormatError(f"payload[{key!r}][{idx}] is malformed: {exc!r}") from exc
    return out


class BeingMemoryPayloadSchemaError(Exception):
    """payload JSON の schema_version が本 service で読めないとき。"""


class BeingMemoryPayloadFormatError(Exception):
    """payload JSON が壊れている / 期待する key が欠けているとき。"""


class SnapshotCoverageError(Exception):
    """snapshot payload が ``EXPECTED_PAYLOAD_KEYS`` を網羅していないとき。

    新しい per-Being store を追加したのに ``capture()`` の dict 生成や
    ``restore()`` の payload 検証を更新し忘れた場合に、起動時 (= 初回 capture)
    に投げて silent failure を構造的に止める。"""


def _validate_snapshot_payload_coverage(
    *,
    emitted_keys: set[str] | frozenset[str],
    expected_keys: set[str] | frozenset[str],
) -> None:
    """emitted_keys が expected_keys を網羅しているか確認する。

    expected_keys にあるのに emitted_keys に無いキーがあれば
    ``SnapshotCoverageError`` を投げる。emitted_keys が expected_keys の
    超集合 (= schema_version など追加キー) であることは許容する。
    """
    missing = expected_keys - emitted_keys
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise SnapshotCoverageError(
            "Snapshot payload misses required keys: "
            f"[{missing_list}]. "
            "新しい per-Being store を追加した場合は EXPECTED_PAYLOAD_KEYS と "
            "capture() / restore() を同時に更新してください。"
        )


class BeingMemorySnapshotService:
    """memory store の状態を Being 単位で JSON 1 本に save / restore する。

    ステートレス: 全 store を constructor で受け取り、``capture`` / ``restore``
    のみが副作用を持つ。

    ``EXPECTED_PAYLOAD_KEYS`` は本 service が capture / restore 両方で扱う
    キーの SSOT。新しい per-Being store を追加するときは:

    1. ``EXPECTED_PAYLOAD_KEYS`` に新 key を足す
    2. ``__init__`` に新 store の引数を追加
    3. ``capture()`` の payload dict に新 key の生成ロジックを追加
    4. ``restore()`` のデコード / 書き戻しに新 key を追加
    5. 足す前の snapshot も読めるようにするなら ``ADDED_PAYLOAD_KEYS`` にも足す
       (design_decisions D1824-6)

    1 だけ足して 3 を忘れると、初回 capture() で ``SnapshotCoverageError``
    が起動時に投げられ silent failure を構造的に防ぐ。
    """

    # PR-F: 本 service が emit / accept する payload key の SSOT。
    # 新 store を足す PR は、ここに 1 行追加 + capture/restore 更新で揃える。
    EXPECTED_PAYLOAD_KEYS: frozenset[str] = frozenset(
        {
            "memory_turn",
            "acquaintances",
            "being_episodes",
            "being_memo_book",
            "being_short_term_memory",
        }
    )
    # 後から足したキー。足す前に保存した snapshot には無いので、無ければ空として読む。
    ADDED_PAYLOAD_KEYS: frozenset[str] = frozenset(
        {
            "being_short_term_memory",
        }
    )

    def __init__(
        self,
        *,
        acquaintance_store: AcquaintanceRepository,
        being_episode_store: EpisodeRepository,
        being_memo_store: MemoBookRepository,
        memory_turn_clock: MemoryTurnClock,
        being_short_term_memory_store: ShortTermMemoryRepository,
    ) -> None:
        if not isinstance(acquaintance_store, AcquaintanceRepository):
            raise TypeError("acquaintance_store must be AcquaintanceRepository")
        if not isinstance(being_episode_store, EpisodeRepository):
            raise TypeError("being_episode_store must be EpisodeRepository")
        if not isinstance(being_memo_store, MemoBookRepository):
            raise TypeError("being_memo_store must be MemoBookRepository")
        if not isinstance(memory_turn_clock, MemoryTurnClock):
            raise TypeError("memory_turn_clock must be MemoryTurnClock")
        if not isinstance(being_short_term_memory_store, ShortTermMemoryRepository):
            raise TypeError("being_short_term_memory_store must be ShortTermMemoryRepository")
        self._acquaintance = acquaintance_store
        self._being_episode = being_episode_store
        self._being_memo = being_memo_store
        self._memory_turn_clock = memory_turn_clock
        self._being_short_term_memory = being_short_term_memory_store

    def capture(self, being_id: BeingId) -> str:
        """各 store から being_id 配下の全状態を読み出し、JSON 文字列で返す。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        payload: dict[str, Any] = {
            "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
        }
        memory_turn = self._memory_turn_clock.current_turn(being_id)
        payload["memory_turn"] = [memory_turn] if memory_turn else []
        payload["acquaintances"] = [acquaintance_to_dict(a) for a in self._acquaintance.list_by_being(being_id)]
        payload["being_episodes"] = [being_episode_to_dict(e) for e in self._being_episode.list_by_being(being_id)]
        payload["being_memo_book"] = [being_memo_to_dict(m) for m in self._being_memo.get(being_id).memos]
        short_term_memory = self._being_short_term_memory.get(being_id)
        payload["being_short_term_memory"] = (
            [] if short_term_memory.is_empty() else [being_short_term_memory_to_dict(short_term_memory)]
        )
        # PR-F: payload key の SSOT である EXPECTED_PAYLOAD_KEYS を全て emit
        # しているか起動時に確認する。新 store を追加して EXPECTED に key を
        # 足したが capture() の dict 生成を忘れた状態を即時に止める。
        _validate_snapshot_payload_coverage(
            emitted_keys=set(payload.keys()),
            expected_keys=self.EXPECTED_PAYLOAD_KEYS,
        )
        return json.dumps(payload, ensure_ascii=False)

    def restore(self, being_id: BeingId, payload_json: str) -> None:
        """payload JSON を 各 store に bulk overwrite で書き戻す。

        **store ごとに順番に書き戻す best-effort 動作**。各 store 内では
        ``replace_all_*_by_being`` が single transaction で atomic だが、
        本 service は **複数 store 跨ぎ atomicity を保証しない**。失敗時は
        呼出側に例外が伝播 (= silent failure 禁止)。詳細は module docstring
        の「restore の atomicity」参照。

        VO 構築時に必要な key が dict から欠けていた場合は
        ``BeingMemoryPayloadFormatError`` に wrap する (= 呼出側で raw
        ``KeyError`` を catch しなくて済む)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(payload_json, str):
            raise TypeError("payload_json must be str")

        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise BeingMemoryPayloadFormatError(f"payload_json is not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise BeingMemoryPayloadFormatError(f"payload root must be object, got {type(payload).__name__}")

        version = payload.get("schema_version")
        if version not in SUPPORTED_PAYLOAD_SCHEMA_VERSIONS:
            raise BeingMemoryPayloadSchemaError(
                f"schema_version={version!r} is not supported (supported: {sorted(SUPPORTED_PAYLOAD_SCHEMA_VERSIONS)})"
            )

        # PR-F: payload key の SSOT である EXPECTED_PAYLOAD_KEYS を一括 validate。
        # 新 store を追加して EXPECTED に key を足したが restore() の検証を
        # 忘れた場合に備え、欠落キーは SnapshotCoverageError ではなく従来通り
        # BeingMemoryPayloadFormatError で報告する (= 形式エラーの一種)。
        payload = {
            **{key: [] for key in self.ADDED_PAYLOAD_KEYS if key not in payload},
            **payload,
        }
        for key in sorted(self.EXPECTED_PAYLOAD_KEYS):
            if key not in payload:
                raise BeingMemoryPayloadFormatError(f"payload missing required key: {key!r}")
            if not isinstance(payload[key], list):
                raise BeingMemoryPayloadFormatError(f"payload[{key!r}] must be list, got {type(payload[key]).__name__}")

        # 形式 validation はここまで。以降は VO へのデコード → bulk write。
        # 個別 VO 構築中の KeyError / ValueError / TypeError は本 service の
        # 例外型に wrap する (= 呼出側が一律 BeingMemoryPayloadFormatError で
        # catch できる)。store 書き戻し中の I/O 例外は素通しさせる
        # (= silent failure を作らない、呼出側に伝播する)。
        memory_turn_raw = payload["memory_turn"]
        if len(memory_turn_raw) > 1 or not all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in memory_turn_raw
        ):
            raise BeingMemoryPayloadFormatError(
                f"payload['memory_turn'] must be [] or [positive int], got {memory_turn_raw!r}"
            )
        memory_turn = memory_turn_raw[0] if memory_turn_raw else 0
        acquaintances = _decode_list(payload["acquaintances"], dict_to_acquaintance, "acquaintances")
        acquaintance_keys = [(a.environment_name, a.name) for a in acquaintances]
        if len(set(acquaintance_keys)) != len(acquaintance_keys):
            raise BeingMemoryPayloadFormatError("payload['acquaintances'] has the same person twice")
        being_episodes = _decode_list(
            payload["being_episodes"],
            lambda data: dict_to_being_episode(data, being_id=being_id),
            "being_episodes",
        )
        for field_name in ("episode_id", "handle"):
            values = [getattr(e, field_name) for e in being_episodes]
            if len(set(values)) != len(values):
                raise BeingMemoryPayloadFormatError(f"payload['being_episodes'] has the same {field_name} twice")
        being_memos = _decode_list(payload["being_memo_book"], dict_to_being_memo, "being_memo_book")
        try:
            being_memo_book = MemoBook(being_id, memos=tuple(being_memos))
        except MemoValidationException as exc:
            raise BeingMemoryPayloadFormatError(f"payload['being_memo_book'] is not a valid memo book: {exc}") from exc
        short_term_raw = payload["being_short_term_memory"]
        if len(short_term_raw) > 1:
            raise BeingMemoryPayloadFormatError(
                f"payload['being_short_term_memory'] must be [] or [one memory], got {len(short_term_raw)} items"
            )
        short_term_memories = _decode_list(
            short_term_raw,
            lambda data: dict_to_being_short_term_memory(data, being_id=being_id),
            "being_short_term_memory",
        )
        short_term_memory = short_term_memories[0] if short_term_memories else ShortTermMemory.empty(being_id)
        self._memory_turn_clock.replace_all_by_being(being_id, turn=memory_turn)
        self._acquaintance.replace_all_by_being(being_id, acquaintances)
        self._being_episode.replace_all_by_being(being_id, being_episodes)
        self._being_memo.replace_all_by_being(being_memo_book)
        self._being_short_term_memory.replace_all_by_being(short_term_memory)


__all__ = [
    "BeingMemorySnapshotService",
    "BeingMemoryPayloadSchemaError",
    "BeingMemoryPayloadFormatError",
    "SnapshotCoverageError",
    "CURRENT_PAYLOAD_SCHEMA_VERSION",
    "SUPPORTED_PAYLOAD_SCHEMA_VERSIONS",
]

"""BeingMemorySnapshotService — Being 単位で 5 memory store を JSON 1 本に save / restore する。

Phase 4 Step 4-2b (Issue #470): run 途中再開 (mid-run resume) を実現するため、
Phase 4-1 で導入した ``BeingSnapshot.memory_payload_json`` (オペーク JSON)
の **中身を作る・読む application service** を提供する。

責務:

- ``capture(being_id) -> str``: 5 store の状態を読み出し、内部 schema v1 の
  JSON 文字列にシリアライズ
- ``restore(being_id, payload_json) -> None``: JSON 文字列を 5 store に
  bulk overwrite で書き戻す。**best-effort: store ごとに順番に書き戻す
  (cross-store atomicity なし)**。各 store 内では Phase 4-2a の
  ``replace_all_*_by_being`` が single-transaction を保証する

## JSON Schema (内部 v1)

```json
{
  "schema_version": 1,
  "memo": [...],
  "semantic_entries": [...],
  "semantic_cluster_signatures": [...],
  "memory_links": [...],
  "recall_buffer_pending": [...],
  "reinterpretation_journal": [...],
  "episodic_episodes": [...]
}
```

各 list の要素 VO ↔ dict は ``_memory_payload_codecs`` モジュールが担当する。
``schema_version`` は本 service が版管理する内部 schema 番号で、
``BeingSnapshot.snapshot_version`` (= VO schema 番号) とは独立に進化させる。

## restore の atomicity

各 store の ``replace_all_*_by_being`` は単一 transaction (sqlite) または
原子的 dict 操作 (in-memory) で **store 内 atomicity を保証する**。一方
本 service は **複数 store に跨る atomicity は保証しない** (= 設計判断、
5 store は独立したリソースで 2-phase commit を導入するコストに見合わない)。
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
from typing import Any

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_memo_entry,
    dict_to_memory_link,
    dict_to_recall_observation,
    dict_to_reinterpretation_entry,
    dict_to_semantic_entry,
    dict_to_subjective_episode,
    memo_entry_to_dict,
    memory_link_to_dict,
    recall_observation_to_dict,
    reinterpretation_entry_to_dict,
    semantic_entry_to_dict,
    subjective_episode_to_dict,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
    EpisodicReinterpretationJournalRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)


CURRENT_PAYLOAD_SCHEMA_VERSION: int = 1
SUPPORTED_PAYLOAD_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


def _decode_list(
    raw_list: list,
    decoder,
    key: str,
):
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
            raise BeingMemoryPayloadFormatError(
                f"payload[{key!r}][{idx}] is malformed: {exc!r}"
            ) from exc
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
    """6 memory store の状態を Being 単位で JSON 1 本に save / restore する。

    ステートレス: 全 store を constructor で受け取り、``capture`` / ``restore``
    のみが副作用を持つ。

    ``EXPECTED_PAYLOAD_KEYS`` は本 service が capture / restore 両方で扱う
    キーの SSOT。新しい per-Being store を追加するときは:

    1. ``EXPECTED_PAYLOAD_KEYS`` に新 key を足す
    2. ``__init__`` に新 store の引数を追加
    3. ``capture()`` の payload dict に新 key の生成ロジックを追加
    4. ``restore()`` のデコード / 書き戻しに新 key を追加

    1 だけ足して 3 を忘れると、初回 capture() で ``SnapshotCoverageError``
    が起動時に投げられ silent failure を構造的に防ぐ。
    """

    # PR-F: 本 service が emit / accept する payload key の SSOT。
    # 新 store を足す PR は、ここに 1 行追加 + capture/restore 更新で揃える。
    EXPECTED_PAYLOAD_KEYS: frozenset[str] = frozenset({
        "memo",
        "semantic_entries",
        "semantic_cluster_signatures",
        "memory_links",
        "recall_buffer_pending",
        "reinterpretation_journal",
        "episodic_episodes",
    })

    def __init__(
        self,
        *,
        memo_store: MemoRepository,
        semantic_store: SemanticMemoryRepository,
        memory_link_store: MemoryLinkRepository,
        recall_buffer_store: EpisodicRecallBufferRepository,
        reinterpretation_journal_store: EpisodicReinterpretationJournalRepository,
        episodic_episode_store: EpisodicEpisodeRepository,
    ) -> None:
        if not isinstance(memo_store, MemoRepository):
            raise TypeError("memo_store must be MemoRepository")
        if not isinstance(semantic_store, SemanticMemoryRepository):
            raise TypeError("semantic_store must be SemanticMemoryRepository")
        if not isinstance(memory_link_store, MemoryLinkRepository):
            raise TypeError("memory_link_store must be MemoryLinkRepository")
        if not isinstance(recall_buffer_store, EpisodicRecallBufferRepository):
            raise TypeError(
                "recall_buffer_store must be EpisodicRecallBufferRepository"
            )
        if not isinstance(
            reinterpretation_journal_store, EpisodicReinterpretationJournalRepository
        ):
            raise TypeError(
                "reinterpretation_journal_store must be EpisodicReinterpretationJournalRepository"
            )
        if not isinstance(episodic_episode_store, EpisodicEpisodeRepository):
            raise TypeError(
                "episodic_episode_store must be EpisodicEpisodeRepository"
            )
        self._memo = memo_store
        self._semantic = semantic_store
        self._memory_link = memory_link_store
        self._recall_buffer = recall_buffer_store
        self._reinterpretation_journal = reinterpretation_journal_store
        self._episodic_episode = episodic_episode_store

    def capture(self, being_id: BeingId) -> str:
        """5 store から being_id 配下の全状態を読み出し、JSON 文字列で返す。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        payload: dict[str, Any] = {
            "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
            "memo": [
                memo_entry_to_dict(e)
                for e in self._memo.list_all_by_being(being_id)
            ],
            "semantic_entries": [
                semantic_entry_to_dict(e)
                for e in self._semantic.list_for_being(being_id)
            ],
            "semantic_cluster_signatures": list(
                self._semantic.list_cluster_signatures_by_being(being_id)
            ),
            "memory_links": [
                memory_link_to_dict(ln)
                for ln in self._memory_link.list_all_links_for_being(being_id)
            ],
            "recall_buffer_pending": [
                recall_observation_to_dict(o)
                for o in self._recall_buffer.list_pending_by_being(being_id)
            ],
            "reinterpretation_journal": [
                reinterpretation_entry_to_dict(e)
                for e in self._reinterpretation_journal.list_all_by_being(being_id)
            ],
            "episodic_episodes": [
                subjective_episode_to_dict(ep)
                for ep in self._episodic_episode.list_all_by_being(being_id)
            ],
        }
        # PR-F: payload key の SSOT である EXPECTED_PAYLOAD_KEYS を全て emit
        # しているか起動時に確認する。新 store を追加して EXPECTED に key を
        # 足したが capture() の dict 生成を忘れた状態を即時に止める。
        _validate_snapshot_payload_coverage(
            emitted_keys=set(payload.keys()),
            expected_keys=self.EXPECTED_PAYLOAD_KEYS,
        )
        return json.dumps(payload, ensure_ascii=False)

    def restore(self, being_id: BeingId, payload_json: str) -> None:
        """payload JSON を 5 store に bulk overwrite で書き戻す。

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
            raise BeingMemoryPayloadFormatError(
                f"payload_json is not valid JSON: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise BeingMemoryPayloadFormatError(
                f"payload root must be object, got {type(payload).__name__}"
            )

        version = payload.get("schema_version")
        if version not in SUPPORTED_PAYLOAD_SCHEMA_VERSIONS:
            raise BeingMemoryPayloadSchemaError(
                f"schema_version={version!r} is not supported "
                f"(supported: {sorted(SUPPORTED_PAYLOAD_SCHEMA_VERSIONS)})"
            )

        # PR-F: payload key の SSOT である EXPECTED_PAYLOAD_KEYS を一括 validate。
        # 新 store を追加して EXPECTED に key を足したが restore() の検証を
        # 忘れた場合に備え、欠落キーは SnapshotCoverageError ではなく従来通り
        # BeingMemoryPayloadFormatError で報告する (= 形式エラーの一種)。
        for key in sorted(self.EXPECTED_PAYLOAD_KEYS):
            if key not in payload:
                raise BeingMemoryPayloadFormatError(
                    f"payload missing required key: {key!r}"
                )
            if not isinstance(payload[key], list):
                raise BeingMemoryPayloadFormatError(
                    f"payload[{key!r}] must be list, got {type(payload[key]).__name__}"
                )

        # 形式 validation はここまで。以降は VO へのデコード → bulk write。
        # 個別 VO 構築中の KeyError / ValueError / TypeError は本 service の
        # 例外型に wrap する (= 呼出側が一律 BeingMemoryPayloadFormatError で
        # catch できる)。store 書き戻し中の I/O 例外は素通しさせる
        # (= silent failure を作らない、呼出側に伝播する)。
        memo_entries = _decode_list(
            payload["memo"], dict_to_memo_entry, "memo"
        )
        semantic_entries = _decode_list(
            payload["semantic_entries"],
            dict_to_semantic_entry,
            "semantic_entries",
        )
        cluster_signatures = [str(s) for s in payload["semantic_cluster_signatures"]]
        memory_links = _decode_list(
            payload["memory_links"], dict_to_memory_link, "memory_links"
        )
        recall_observations = _decode_list(
            payload["recall_buffer_pending"],
            dict_to_recall_observation,
            "recall_buffer_pending",
        )
        journal_entries = _decode_list(
            payload["reinterpretation_journal"],
            dict_to_reinterpretation_entry,
            "reinterpretation_journal",
        )
        episodes = _decode_list(
            payload["episodic_episodes"],
            dict_to_subjective_episode,
            "episodic_episodes",
        )

        # 順序は「依存の少ない方から」: memo / semantic は他 store に依存しない、
        # memory_link / reinterpretation_journal / recall_buffer は episode に
        # 参照するが、本 service は参照整合性まで保証しない (= 各 store 独立)。
        self._memo.replace_all_by_being(being_id, memo_entries)
        self._semantic.replace_all_by_being(
            being_id, semantic_entries, cluster_signatures
        )
        self._memory_link.replace_all_by_being(being_id, memory_links)
        self._recall_buffer.replace_all_pending_by_being(
            being_id, recall_observations
        )
        self._reinterpretation_journal.replace_all_by_being(
            being_id, journal_entries
        )
        self._episodic_episode.replace_all_by_being(being_id, episodes)


__all__ = [
    "BeingMemorySnapshotService",
    "BeingMemoryPayloadSchemaError",
    "BeingMemoryPayloadFormatError",
    "SnapshotCoverageError",
    "CURRENT_PAYLOAD_SCHEMA_VERSION",
    "SUPPORTED_PAYLOAD_SCHEMA_VERSIONS",
]

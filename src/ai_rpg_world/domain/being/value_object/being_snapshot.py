"""BeingSnapshot — Being 集約のシリアライズ可能な不変表現。

PR #462 §2.1 R1: 「永続化は store 単位 env ではなく Being 単位の設定 1 箇所」「復元
の完全性は all-or-nothing で保証 (部分復元を構造的に禁止)」を実現するための中間
形式。Phase 2 PR4 (旧) では Being 集約 root の状態 (identity + attachment +
declared_memory_kinds) のみを内包していた。

Phase 4 Step 4-1 (Issue #470): memory payload を載せるための ``snapshot_version=2``
を導入する。memory payload 自体は **オペーク な JSON 文字列** として保持し、
store ごとの内訳構造は ``BeingMemorySnapshotService`` (application 層) が
担当する。これにより:

- domain/being/ から各 memory context (memo / semantic / memory_link /
  recall_buffer / reinterpretation_journal / episodic_episode) への依存を
  避けられる (= primitive-only snapshot の設計哲学を維持)
- 将来 memory store の VO 形が変わっても、本 VO の schema は変えなくてよい
  (application 層の codec が JSON schema を版管理する)
- v1 snapshot (memory payload なし) と v2 snapshot (memory payload あり)
  の両方を構造的に扱える

## 不変条件 (all-or-nothing 構造の核)

1. ``being_id_value`` / ``identity_name`` / ``identity_first_person`` は非空
2. ``attachment_world_id`` と ``attachment_player_id`` は **両方 None または両方
   非 None** でなければならない (= 片方だけ埋まる部分状態を構造的に禁止)
3. ``declared_memory_kinds`` は str のタプル (中身が認識可能な MemoryKind 値か
   どうかは codec の decode 時にチェックする = VO 自体は形式のみガード)
4. ``snapshot_version`` は正の int
5. ``memory_payload_json`` は ``str | None`` (= 非 None なら JSON valid を
   codec が責務として保証)。v1 snapshot では常に None

これらが満たされない場合は ``BeingSnapshotIncompleteException`` を投げる。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
)


CURRENT_SNAPSHOT_VERSION: int = 2
LEGACY_SNAPSHOT_VERSION_V1: int = 1


@dataclass(frozen=True)
class BeingSnapshot:
    """Being 集約のシリアライズ可能な不変表現。

    Phase 4 Step 4-1: ``memory_payload_json`` で memory store 群の状態を
    オペーク JSON として保持できるようになった (= v2)。v1 互換のため
    ``memory_payload_json=None`` も許容する。
    """

    being_id_value: str
    identity_name: str
    identity_first_person: str
    attachment_world_id: int | None
    attachment_player_id: int | None
    declared_memory_kinds: tuple[str, ...]
    snapshot_version: int = CURRENT_SNAPSHOT_VERSION
    memory_payload_json: str | None = None

    def __post_init__(self) -> None:
        self._reject_blank("being_id_value", self.being_id_value)
        self._reject_blank("identity_name", self.identity_name)
        self._reject_blank("identity_first_person", self.identity_first_person)
        self._validate_attachment_pair()
        self._validate_memory_kinds()
        self._validate_version()
        self._validate_memory_payload()

    @staticmethod
    def _reject_blank(field: str, value: object) -> None:
        if not isinstance(value, str):
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot.{field} must be str, got {type(value).__name__}"
            )
        if not value.strip():
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot.{field} must be non-empty"
            )

    def _validate_attachment_pair(self) -> None:
        world = self.attachment_world_id
        player = self.attachment_player_id
        if (world is None) ^ (player is None):
            raise BeingSnapshotIncompleteException(
                "BeingSnapshot attachment fields must be both None or both set; "
                f"got world_id={world!r}, player_id={player!r}"
            )
        if world is not None and not isinstance(world, int):
            raise BeingSnapshotIncompleteException(
                f"attachment_world_id must be int or None, got {type(world).__name__}"
            )
        if player is not None and not isinstance(player, int):
            raise BeingSnapshotIncompleteException(
                f"attachment_player_id must be int or None, got {type(player).__name__}"
            )

    def _validate_memory_kinds(self) -> None:
        if not isinstance(self.declared_memory_kinds, tuple):
            raise BeingSnapshotIncompleteException(
                "declared_memory_kinds must be tuple, "
                f"got {type(self.declared_memory_kinds).__name__}"
            )
        for kind in self.declared_memory_kinds:
            if not isinstance(kind, str):
                raise BeingSnapshotIncompleteException(
                    "declared_memory_kinds elements must be str, "
                    f"got {type(kind).__name__}"
                )

    def _validate_version(self) -> None:
        # bool は int 派生なので True/False が黙って通らないよう明示的に排除する。
        if (
            isinstance(self.snapshot_version, bool)
            or not isinstance(self.snapshot_version, int)
            or self.snapshot_version <= 0
        ):
            raise BeingSnapshotIncompleteException(
                f"snapshot_version must be positive int, got {self.snapshot_version!r}"
            )

    def _validate_memory_payload(self) -> None:
        """memory_payload_json は ``str | None`` のみ許容。

        中身が JSON valid かどうかは codec 側で encode/decode 時にチェック
        する責務とする (= VO は形式のみガードする方針と一貫)。
        """
        if self.memory_payload_json is None:
            return
        if not isinstance(self.memory_payload_json, str):
            raise BeingSnapshotIncompleteException(
                "memory_payload_json must be str or None, "
                f"got {type(self.memory_payload_json).__name__}"
            )
        # 空文字列は JSON としても不正で、has_memory_payload=True なのに中身が
        # 空という呼び出し元混乱を生むので構造的に弾く (= None と区別する意義
        # を保つ)。
        if not self.memory_payload_json:
            raise BeingSnapshotIncompleteException(
                "memory_payload_json must be non-empty when not None"
            )

    @property
    def has_attachment(self) -> bool:
        """attachment 情報を持つ snapshot なら True。"""
        return self.attachment_world_id is not None

    @property
    def has_memory_payload(self) -> bool:
        """memory payload を持つ snapshot なら True (= v2 で有効化された経路)。"""
        return self.memory_payload_json is not None


__all__ = [
    "BeingSnapshot",
    "CURRENT_SNAPSHOT_VERSION",
    "LEGACY_SNAPSHOT_VERSION_V1",
]

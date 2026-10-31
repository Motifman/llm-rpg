"""BeingSnapshot — Being 集約のシリアライズ可能な不変表現。

PR #462 §2.1 R1: 「永続化は store 単位 env ではなく Being 単位の設定 1 箇所」「復元
の完全性は all-or-nothing で保証 (部分復元を構造的に禁止)」を実現するための中間
形式。Being 集約 root の状態 (人柄と attachment) を持つ。

Phase 4 Step 4-1 (Issue #470): memory payload を載せるための ``snapshot_version=2``
を導入する。memory payload 自体は **オペーク な JSON 文字列** として保持し、
store ごとの内訳構造は ``BeingMemorySnapshotService`` (application 層) が
担当する。これにより:

- domain/being/ から各 memory context (memo など) への依存を
  避けられる (= primitive-only snapshot の設計哲学を維持)
- 将来 memory store の VO 形が変わっても、本 VO の schema は変えなくてよい
  (application 層の codec が JSON schema を版管理する)
- v1 snapshot (memory payload なし) と v2 snapshot (memory payload あり)
  の両方を構造的に扱える

## 不変条件 (all-or-nothing 構造の核)

1. ``being_id_value`` は非空。人柄は ``Persona`` が自分で検証する。人柄が ``None`` なのは、``persona`` の無い古い
   snapshot から読んだときだけで、そのときは読み捨てる名前と一人称を ``legacy_identity_*`` に持つ
2. ``attachment_environment_id`` と ``attachment_environment_name`` は **両方 None または両方
   空でない文字列** でなければならない (= 片方だけ埋まる部分状態を構造的に禁止)。古い snapshot の番号
   (``legacy_attachment_*``) も同じく両方そろう
3. ``snapshot_version`` は正の int
4. ``memory_payload_json`` は ``str | None`` (= 非 None なら JSON valid を
   codec が責務として保証)。v1 snapshot では常に None
5. ``legacy_declared_memory_kinds`` は str のタプル。古い snapshot から読んだときだけ埋まり、書き出さない

これらが満たされない場合は ``BeingSnapshotIncompleteException`` を投げる。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.persona import Persona
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
    #: ``persona`` の無い古い snapshot から読んだときだけ None。名前と一人称は読み捨て、起動時にシナリオから入れた
    #: 人柄で埋めてから decode する (design_decisions D1469-2)。
    persona: Persona | None
    #: Being が入っていた環境の識別子と表示の名前 (design_decisions D1928-2)。入っていなければ両方 None。
    attachment_environment_id: str | None
    attachment_environment_name: str | None
    snapshot_version: int = CURRENT_SNAPSHOT_VERSION
    memory_payload_json: str | None = None
    #: 消した「どの種類の記憶を持つかの宣言」。古い snapshot から読んだときだけ埋まる。読み捨てた件数を
    #: ``snapshot_load`` に残すためだけに持ち、書き出さない (design_decisions D1469-1)。
    legacy_declared_memory_kinds: tuple[str, ...] = ()
    #: 古い snapshot の ``identity_name`` と ``identity_first_person``。読み捨てたことを ``snapshot_load`` に
    #: 残すためだけに持ち、書き出さない (design_decisions D1469-2)。
    legacy_identity_name: str | None = None
    legacy_identity_first_person: str | None = None
    #: 環境の識別子の無い古い snapshot の、世界とプレイヤーの番号。「プレイヤー → Being」の対応表を作り直すのにだけ
    #: 使い、書き出さない (design_decisions D1928、D1928-2)。
    legacy_attachment_world_id: int | None = None
    legacy_attachment_player_id: int | None = None

    def __post_init__(self) -> None:
        self._reject_blank("being_id_value", self.being_id_value)
        self._validate_persona()
        self._validate_attachment_pair()
        self._validate_memory_kinds()
        self._validate_version()
        self._validate_memory_payload()

    def _validate_persona(self) -> None:
        if self.persona is None:
            if not isinstance(self.legacy_identity_name, str):
                raise BeingSnapshotIncompleteException("BeingSnapshot without persona must carry legacy_identity_name")
            return
        if not isinstance(self.persona, Persona):
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot.persona must be Persona or None, got {type(self.persona).__name__}"
            )

    @property
    def has_legacy_identity(self) -> bool:
        """``persona`` の無い古い snapshot から読んだなら True。"""
        return self.persona is None

    @staticmethod
    def _reject_blank(field: str, value: object) -> None:
        if not isinstance(value, str):
            raise BeingSnapshotIncompleteException(f"BeingSnapshot.{field} must be str, got {type(value).__name__}")
        if not value.strip():
            raise BeingSnapshotIncompleteException(f"BeingSnapshot.{field} must be non-empty")

    def _validate_attachment_pair(self) -> None:
        self._require_both_or_neither(
            "attachment_environment", self.attachment_environment_id, self.attachment_environment_name, str
        )
        for field in ("attachment_environment_id", "attachment_environment_name"):
            value = getattr(self, field)
            if value is not None and not value.strip():
                raise BeingSnapshotIncompleteException(f"{field} must be non-blank")
        self._require_both_or_neither(
            "legacy_attachment", self.legacy_attachment_world_id, self.legacy_attachment_player_id, int
        )

    @staticmethod
    def _require_both_or_neither(label: str, first: object, second: object, kind: type) -> None:
        if (first is None) ^ (second is None):
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot {label} fields must be both None or both set; got {first!r}, {second!r}"
            )
        for value in (first, second):
            if value is not None and (not isinstance(value, kind) or isinstance(value, bool)):
                raise BeingSnapshotIncompleteException(
                    f"BeingSnapshot {label} fields must be {kind.__name__} or None, got {type(value).__name__}"
                )

    def _validate_memory_kinds(self) -> None:
        if not isinstance(self.legacy_declared_memory_kinds, tuple):
            raise BeingSnapshotIncompleteException(
                f"legacy_declared_memory_kinds must be tuple, got {type(self.legacy_declared_memory_kinds).__name__}"
            )
        for kind in self.legacy_declared_memory_kinds:
            if not isinstance(kind, str):
                raise BeingSnapshotIncompleteException(
                    f"legacy_declared_memory_kinds elements must be str, got {type(kind).__name__}"
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
                f"memory_payload_json must be str or None, got {type(self.memory_payload_json).__name__}"
            )
        # 空文字列は JSON としても不正で、has_memory_payload=True なのに中身が
        # 空という呼び出し元混乱を生むので構造的に弾く (= None と区別する意義
        # を保つ)。
        if not self.memory_payload_json:
            raise BeingSnapshotIncompleteException("memory_payload_json must be non-empty when not None")

    @property
    def has_attachment(self) -> bool:
        """attachment 情報を持つ snapshot なら True。"""
        return self.attachment_environment_id is not None

    @property
    def has_memory_payload(self) -> bool:
        """memory payload を持つ snapshot なら True (= v2 で有効化された経路)。"""
        return self.memory_payload_json is not None


__all__ = [
    "BeingSnapshot",
    "CURRENT_SNAPSHOT_VERSION",
    "LEGACY_SNAPSHOT_VERSION_V1",
]

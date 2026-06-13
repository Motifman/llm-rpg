"""Being 集約ルート。

「経験を持つ AI」の主体。世界・run を跨いで永続化される第一級のドメイン概念。

Phase 2 PR1: 最小骨格 (BeingId + BeingIdentity)
Phase 2 PR2: attachments を追加 (0..1)
Phase 2 PR3 (本 PR): declared_memory_kinds を追加 (= memory_refs の薄い宣言形式)
後続 PR で順次:
- all-or-nothing snapshot/restore loader
- habits (System 1 キャッシュ)

集約の粒度方針 (PR #462 §4 起案者推し): (b) **being_id を共有キーにした
store 連合 + all-or-nothing loader** から始める。記憶 store は書き込み頻度が
高く、集約に閉じるとロック競合するため、本 aggregate root は薄い identity
core を保持する。
"""

from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingAlreadyAttachedException,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot


class Being(AggregateRoot):
    """Being 集約ルート。"""

    def __init__(
        self,
        being_id: BeingId,
        identity: BeingIdentity,
        attachment: BeingAttachment | None = None,
        declared_memory_kinds: Iterable[MemoryKind] = (),
    ) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        if not isinstance(identity, BeingIdentity):
            raise TypeError(
                f"identity must be BeingIdentity, got {type(identity).__name__}"
            )
        if attachment is not None and not isinstance(attachment, BeingAttachment):
            raise TypeError(
                f"attachment must be BeingAttachment or None, "
                f"got {type(attachment).__name__}"
            )
        validated: list[MemoryKind] = []
        for kind in declared_memory_kinds:
            if not isinstance(kind, MemoryKind):
                raise TypeError(
                    f"declared_memory_kinds must contain MemoryKind, "
                    f"got {type(kind).__name__}"
                )
            validated.append(kind)
        self._being_id = being_id
        self._identity = identity
        self._attachment: BeingAttachment | None = attachment
        self._declared_memory_kinds: frozenset[MemoryKind] = frozenset(validated)

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def identity(self) -> BeingIdentity:
        return self._identity

    @property
    def attachment(self) -> BeingAttachment | None:
        """現在の attachment。未 attach なら None。"""
        return self._attachment

    @property
    def is_attached(self) -> bool:
        """attachment を持っていれば True。"""
        return self._attachment is not None

    @property
    def declared_memory_kinds(self) -> frozenset[MemoryKind]:
        """Being が所有を宣言する記憶 store の種類集合。

        all-or-nothing snapshot/restore loader (Phase 2 PR4 予定) は本集合を
        見て、対応 Repository から being_id keyed で load する。Being 集約
        自体は記憶インスタンスを保持せず、宣言だけを持つ (= 集約粒度方針
        (b) に従う薄い宣言形式)。
        """
        return self._declared_memory_kinds

    def declares(self, kind: MemoryKind) -> bool:
        """指定 ``kind`` を所有宣言していれば True。"""
        return kind in self._declared_memory_kinds

    def with_declared_memory_kinds(
        self, kinds: Iterable[MemoryKind]
    ) -> "Being":
        """``declared_memory_kinds`` を差し替えた新しい Being を返す。

        集約 root の不変性 (= identity / being_id) は維持し、宣言集合だけを
        更新するための副作用なし API。既存 attachment はそのまま引き継ぐ。
        要素の型チェックはコンストラクタに委譲する (= 二重実装を避ける)。
        """
        return Being(
            being_id=self._being_id,
            identity=self._identity,
            attachment=self._attachment,
            declared_memory_kinds=kinds,
        )

    def attach(self, attachment: BeingAttachment) -> None:
        """world / player に attach する。

        既に attachment を持っている場合は ``BeingAlreadyAttachedException``。
        乗り換える場合は先に ``detach`` を呼ぶ。
        """
        if not isinstance(attachment, BeingAttachment):
            raise TypeError(
                f"attachment must be BeingAttachment, got {type(attachment).__name__}"
            )
        if self._attachment is not None:
            raise BeingAlreadyAttachedException(
                f"Being({self._being_id}) is already attached to "
                f"{self._attachment}; detach first to switch"
            )
        self._attachment = attachment

    def detach(self) -> BeingAttachment | None:
        """attachment を解除し、解除前の値を返す。未 attach なら None。

        detach しても経験は Being 集約 (および being_id を共有キーにした
        各記憶 store) に残る (PR #462 §2.1 R1)。
        """
        previous = self._attachment
        self._attachment = None
        return previous

    def __repr__(self) -> str:
        return (
            f"Being(being_id={self._being_id!r}, identity={self._identity!r}, "
            f"attachment={self._attachment!r}, "
            f"declared_memory_kinds={sorted(k.value for k in self._declared_memory_kinds)!r})"
        )


__all__ = ["Being"]

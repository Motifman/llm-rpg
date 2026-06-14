"""BeingProvisioningService — LLM 制御 player に Being を確保する application service。

Issue #470 Phase 3 Step 6-mini: 既存 wiring が PlayerId 中心で動いているため、
Step 3a-2 以降の caller 移行で BeingAttachmentResolver が Being を引けるよう、
LLM ターン開始時に (world, player) に Being が attach されていることを保証する。

## 責務

- ある (world, player) ペアに Being が attach 中なら何もしない (= idempotent)
- attach 中の Being が無ければ、決定論的な BeingId で Being を作って attach する
- 既に同 BeingId の Being が別 (world, player) に attach 中なら detach → 再 attach

## 決定論的 BeingId 命名

``f"being_w{world_id.value}_p{player_id.value}"`` を仮の命名規約として使う。
- run を跨いで同じ player_id が出てきたら同じ BeingId に決まる (= 永続化と再開で identity が連続する)
- Step 6-full で wiring が Being-centric になった時に、本 service を経由せず persona
  config 等から explicit BeingId を渡す経路に置き換える前提

## Identity の placeholder

``identity_hint`` を渡せばそれを使う。渡されなければ ``BeingIdentity(name=f"agent_{player_id.value}",
first_person="わたし")`` を default として使う (= 後で persona と結合する想定の仮値)。

## Thread safety

本 service は単一スレッドの LLM ターン実行を前提とする。並行 ``ensure_attached``
は race するので、必要なら呼び出し側で lock を取ること (= 現状 K run は単一スレッド
LLM 実行なので問題なし)。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingProvisioningService:
    """LLM 制御 player に Being を確保する idempotent な service。"""

    def __init__(
        self,
        being_repository: BeingRepository,
        *,
        default_world_id: WorldId | None = None,
    ) -> None:
        if not isinstance(being_repository, BeingRepository):
            raise TypeError(
                "being_repository must be BeingRepository, "
                f"got {type(being_repository).__name__}"
            )
        if default_world_id is not None and not isinstance(default_world_id, WorldId):
            raise TypeError(
                "default_world_id must be WorldId or None, "
                f"got {type(default_world_id).__name__}"
            )
        self._repo = being_repository
        self._default_world_id = default_world_id or WorldId(1)
        self._resolver = BeingAttachmentResolver(being_repository)

    @property
    def default_world_id(self) -> WorldId:
        return self._default_world_id

    def ensure_attached(
        self,
        player_id: PlayerId,
        *,
        world_id: WorldId | None = None,
        identity_hint: BeingIdentity | None = None,
    ) -> BeingId:
        """指定 (world, player) に Being が attach されていることを保証する。

        - 既に attach 済みの Being があれば、その BeingId を返す
        - 無ければ ``f"being_w{world_id}_p{player_id}"`` で Being を作って attach
        - 既存の同 BeingId が別 (world, player) に attach 中なら detach → 再 attach
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError(
                f"player_id must be PlayerId, got {type(player_id).__name__}"
            )
        if world_id is not None and not isinstance(world_id, WorldId):
            raise TypeError(
                f"world_id must be WorldId or None, got {type(world_id).__name__}"
            )
        if identity_hint is not None and not isinstance(identity_hint, BeingIdentity):
            raise TypeError(
                "identity_hint must be BeingIdentity or None, "
                f"got {type(identity_hint).__name__}"
            )

        target_world = world_id or self._default_world_id

        # Case 1: 既に (world, player) に attach 中の Being があればそのまま返す
        existing = self._resolver.resolve_attached_being(target_world, player_id)
        if existing is not None:
            return existing.being_id

        # Case 2: 決定論 BeingId で Being が既に存在するなら、それを (world, player)
        # に attach し直す (= 別箇所に attach 中なら detach してから)。
        #
        # NOTE: ``find_by_id`` は ``BeingSnapshotCodec.decode`` 経由で **毎回
        # 新インスタンス** を返す (Phase 4 Step 4-3 以降、InMemory / Sqlite 共)。
        # 参照共有はないので、ここで mutate しても repo の内部状態は変わらない。
        # **必ず ``save()`` を呼んで永続化すること**。
        being_id = self._derive_being_id(target_world, player_id)
        existing_being = self._repo.find_by_id(being_id)
        if existing_being is not None:
            if existing_being.is_attached:
                existing_being.detach()
            existing_being.attach(
                BeingAttachment(world_id=target_world, player_id=player_id)
            )
            self._repo.save(existing_being)
            return being_id

        # Case 3: 新規作成 + attach
        identity = identity_hint or self._default_identity(player_id)
        being = Being(
            being_id=being_id,
            identity=identity,
            attachment=BeingAttachment(world_id=target_world, player_id=player_id),
        )
        self._repo.save(being)
        return being_id

    @staticmethod
    def _derive_being_id(world_id: WorldId, player_id: PlayerId) -> BeingId:
        """決定論的 BeingId 命名規約 (= ``being_w<world>_p<player>``)。

        Phase 3 までの仮命名。Step 6-full で persona config 由来の explicit ID に
        差し替える想定。
        """
        return BeingId(f"being_w{world_id.value}_p{player_id.value}")

    @staticmethod
    def _default_identity(player_id: PlayerId) -> BeingIdentity:
        """``identity_hint`` が渡されない場合の placeholder。後で persona と結合する想定。"""
        return BeingIdentity(
            name=f"agent_{player_id.value}",
            first_person="わたし",
        )


__all__ = ["BeingProvisioningService"]

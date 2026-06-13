"""BeingAttachmentResolver — BeingId ↔ PlayerId の双方向解決ドメインサービス。

Issue #470 Phase 3 Step 2: Phase 3 全体ロードマップにおける「橋渡し」層。
既存コードは ``PlayerId`` で動き、新コードは ``BeingId`` で書きたい。両者を
``Being.attachment`` 経由で繋ぐ単一窓口。

## 不変条件

PR #462 §2.1 R1 / Phase 2 PR2 が示す ``attachment は 0..1`` を前提とする:

- ある (world, player) ペアに attach 中の Being は **高々 1 つ**
- ある Being の attachment も **高々 1 つ**

正常系では戻り値は単数 (``BeingId | None`` / ``PlayerId | None``)。仮に
Repository から複数返ってきたら ``BeingMultipleAttachmentException`` を
投げる (= 不変条件の破れを早期検出)。

## なぜ 0..1 を Resolver でも検査するか

``Being.attach`` で多重 attach は弾いているが、

- 永続化された DB から読み戻した時の異常データ
- 直接 Repository を書く経路 (= aggregate ロジックを迂回)
- マイグレーションのバグ

など、aggregate を経由しない経路で不変条件が壊れる可能性がある。**Resolver
は ID 解決の集中点なので、ここで検査することで影響を局所化する**。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingMultipleAttachmentException,
)
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingAttachmentResolver:
    """BeingId ↔ PlayerId の双方向解決を行うドメインサービス。"""

    def __init__(self, being_repository: BeingRepository) -> None:
        if not isinstance(being_repository, BeingRepository):
            raise TypeError(
                "being_repository must be BeingRepository, "
                f"got {type(being_repository).__name__}"
            )
        self._repo = being_repository

    def resolve_attached_being(
        self, world_id: WorldId, player_id: PlayerId
    ) -> Being | None:
        """(world, player) に attach 中の Being を返す。

        - 0 件: ``None``
        - 1 件: その Being
        - 2 件以上: ``BeingMultipleAttachmentException`` (= 0..1 不変条件違反)
        """
        if not isinstance(world_id, WorldId):
            raise TypeError(
                f"world_id must be WorldId, got {type(world_id).__name__}"
            )
        if not isinstance(player_id, PlayerId):
            raise TypeError(
                f"player_id must be PlayerId, got {type(player_id).__name__}"
            )

        matches = self._repo.find_all_attached_to(world_id, player_id)
        if not matches:
            return None
        if len(matches) > 1:
            raise BeingMultipleAttachmentException(
                f"multiple Beings attached to (world={world_id}, player={player_id}): "
                f"{[b.being_id.value for b in matches]}"
            )
        return matches[0]

    def resolve_being_id(
        self, world_id: WorldId, player_id: PlayerId
    ) -> BeingId | None:
        """(world, player) に attach 中の Being の ID を返す。0..1。

        他 resolve メソッドと型ガードの揃いを取るため、委譲前にも明示的に
        チェックする (= 将来 resolve_attached_being のシグネチャが変わっても
        本メソッド単体でガードされる)。
        """
        if not isinstance(world_id, WorldId):
            raise TypeError(
                f"world_id must be WorldId, got {type(world_id).__name__}"
            )
        if not isinstance(player_id, PlayerId):
            raise TypeError(
                f"player_id must be PlayerId, got {type(player_id).__name__}"
            )
        being = self.resolve_attached_being(world_id, player_id)
        return being.being_id if being is not None else None

    def resolve_player_id(self, being_id: BeingId) -> PlayerId | None:
        """Being の現在の attachment.player_id を返す。

        - Being が存在しない: ``None``
        - Being は存在するが detach 中: ``None``
        - attach 中: その ``PlayerId``
        """
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        being = self._repo.find_by_id(being_id)
        if being is None or being.attachment is None:
            return None
        return being.attachment.player_id


__all__ = ["BeingAttachmentResolver"]

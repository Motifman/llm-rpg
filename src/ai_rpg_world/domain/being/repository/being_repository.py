"""BeingRepository — Being 集約の永続化抽象。

PR #462 §2.1 (R1): ``save/load = ビーイング丸ごとの snapshot/restore``。
本 PR (Phase 2 PR1) では Being 集約自体が最小構成 (BeingId + Identity) の
ため、Repository も基本 CRUD のみを定義する。

後続 PR で all-or-nothing snapshot/restore (= 全 store が揃って初めて load 成功)
の意味論を導入する際は、本 interface を拡張 or wrap する形を取る。

NOTE: ``domain/common/repository.py::Repository[T, ID]`` 基底を継承せず ABC 直継承
にしているのは、本 PR 段階では Being 集約自体が最小構成であり、汎用基底が要求する
``find_by_ids`` / ``find_all`` は YAGNI (= 必要になった時点で追加)。Phase 1 の
memory Repository 群 (例: ``EpisodicEpisodeRepository``) と同じ方針。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingRepository(ABC):
    """Being 集約の永続化リポジトリ抽象。"""

    @abstractmethod
    def save(self, being: Being) -> None:
        """Being を保存する。同一 ``BeingId`` は上書き (upsert)。"""

    @abstractmethod
    def find_by_id(self, being_id: BeingId) -> Being | None:
        """指定 ID の Being を返す。存在しなければ ``None``。"""

    @abstractmethod
    def exists(self, being_id: BeingId) -> bool:
        """指定 ID の Being が存在すれば True。"""

    @abstractmethod
    def delete(self, being_id: BeingId) -> bool:
        """Being を削除する。存在しなければ False。"""

    @abstractmethod
    def save_snapshot(self, snapshot: BeingSnapshot) -> None:
        """payload を載せた ``BeingSnapshot`` を直接受け取って保存する入口。

        Phase 4 Step 4-3 (Issue #470): ``BeingPersistenceService`` が memory
        payload 込みの v2 snapshot を保存するためにこちらを呼ぶ。``save(being)``
        は codec で payload=None の snapshot を encode した上で本メソッドに
        delegate する形に整理されている。同一 ``BeingId`` は upsert。
        """

    @abstractmethod
    def find_snapshot_by_id(self, being_id: BeingId) -> BeingSnapshot | None:
        """指定 ID の ``BeingSnapshot`` を返す (codec decode を経由しない経路)。

        Phase 4 Step 4-3: ``BeingPersistenceService`` が payload を読み出し
        memory restore に回すための入口。``find_by_id`` は codec.decode が
        払い落とした Being aggregate しか返さないので、payload を残した
        snapshot 取得の経路を別に持つ必要がある。
        """

    @abstractmethod
    def find_all_attached_to(
        self, world_id: WorldId, player_id: PlayerId
    ) -> list[Being]:
        """指定 (world, player) に attach 中の Being をすべて返す。

        正常系では 0..1 件しか返らない (= ``Being.attach`` で 0..1 を強制)。
        2 件以上返るのは attach 制約が破られた異常状態なので、
        ``BeingAttachmentResolver`` 等の呼び出し元で検出して
        ``BeingMultipleAttachmentException`` を投げる。

        本 interface 自体はリスト返却に留め、不変条件の判定は domain service
        側に委ねる (= Repository は「集約の取り出し器」、judgement は service)。
        """


__all__ = ["BeingRepository"]

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


__all__ = ["BeingRepository"]

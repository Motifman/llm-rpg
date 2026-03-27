from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING
from ai_rpg_world.domain.common.repository import ReadRepository, Repository
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class MonsterRepository(Repository[MonsterAggregate, MonsterId]):
    """モンスター集約のリポジトリインターフェース"""

    @abstractmethod
    def generate_monster_id(self) -> MonsterId:
        """新しい MonsterId を発行する（ID発行はリポジトリの責務）。"""
        pass

    @abstractmethod
    def generate_world_object_id_for_npc(self) -> WorldObjectId:
        """NPC用の WorldObjectId を発行する（新規モンスター出現時に使用）。"""
        pass

    @abstractmethod
    def find_by_world_object_id(self, world_object_id: WorldObjectId) -> Optional[MonsterAggregate]:
        """WorldObjectIdに紐づくモンスターを検索"""
        pass

    @abstractmethod
    def find_by_spot_id(self, spot_id: "SpotId") -> List[MonsterAggregate]:
        """指定スポットに紐づくモンスター一覧を取得（ALIVE/DEAD 問わず）。"""
        pass


class MonsterTemplateRepository(ReadRepository[MonsterTemplate, MonsterTemplateId]):
    """モンスターテンプレートのリポジトリインターフェース"""

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[MonsterTemplate]:
        """名前でモンスターテンプレートを検索"""
        pass


class MonsterTemplateWriter(ABC):
    """モンスターテンプレートの投入専用 writer ポート"""

    @abstractmethod
    def replace_template(self, template: MonsterTemplate) -> None:
        """テンプレートを丸ごと置き換える。"""
        pass

    @abstractmethod
    def delete_template(self, template_id: MonsterTemplateId) -> bool:
        """テンプレートを削除する。"""
        pass
